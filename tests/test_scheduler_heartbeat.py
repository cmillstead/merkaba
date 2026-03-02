# tests/test_scheduler_heartbeat.py
"""Tests for heartbeat checklist integration into the scheduler."""

import time
from pathlib import Path

from merkaba.orchestration.queue import TaskQueue
from merkaba.orchestration.scheduler import Scheduler


def _make_scheduler(tmp_path: Path) -> Scheduler:
    """Create a Scheduler backed by a temp-dir TaskQueue."""
    db = str(tmp_path / "tasks.db")
    queue = TaskQueue(db_path=db)
    return Scheduler(queue=queue, merkaba_home=tmp_path)


def test_heartbeat_creates_task_for_due_item(tmp_path):
    """Unchecked items with schedules should create tasks when file is present."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        "# Heartbeat\n\n"
        "- [ ] Check email (every 30m)\n"
        "- [ ] Review logs (daily)\n"
    )
    sched = _make_scheduler(tmp_path)
    created = sched._check_heartbeat()
    assert len(created) == 2
    # Tasks should exist in the queue
    tasks = sched.queue.list_tasks()
    assert any(t["name"] == "heartbeat: Check email" for t in tasks)
    assert any(t["name"] == "heartbeat: Review logs" for t in tasks)
    # All should be heartbeat type
    assert all(t["task_type"] == "heartbeat" for t in tasks if t["name"].startswith("heartbeat:"))


def test_heartbeat_skips_checked_items(tmp_path):
    """Checked items (done) should not create tasks."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        "- [x] Already done (daily)\n"
        "- [ ] Still pending (every 1h)\n"
    )
    sched = _make_scheduler(tmp_path)
    created = sched._check_heartbeat()
    assert len(created) == 1
    assert created[0]["name"] == "heartbeat: Still pending"


def test_heartbeat_skips_items_without_schedule(tmp_path):
    """Items without a schedule are informational — no task created."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        "- [ ] Remember to update docs\n"
        "- [ ] Check email (every 30m)\n"
    )
    sched = _make_scheduler(tmp_path)
    created = sched._check_heartbeat()
    assert len(created) == 1
    assert created[0]["name"] == "heartbeat: Check email"


def test_heartbeat_mtime_avoids_reparse(tmp_path):
    """Unchanged files should not be re-parsed on second tick."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("- [ ] Check email (every 30m)\n")
    sched = _make_scheduler(tmp_path)

    # First call parses and creates tasks
    created1 = sched._check_heartbeat()
    assert len(created1) == 1

    # Second call — mtime unchanged, should not re-parse (no new tasks)
    created2 = sched._check_heartbeat()
    assert len(created2) == 0


def test_heartbeat_reparses_on_mtime_change(tmp_path):
    """Modified files should be re-parsed."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("- [ ] Check email (every 30m)\n")
    sched = _make_scheduler(tmp_path)

    created1 = sched._check_heartbeat()
    assert len(created1) == 1

    # Touch the file to bump mtime (sleep ensures different mtime)
    time.sleep(0.05)
    hb.write_text(
        "- [ ] Check email (every 30m)\n"
        "- [ ] New item (hourly)\n"
    )

    created2 = sched._check_heartbeat()
    assert len(created2) == 1  # Only the new item
    assert created2[0]["name"] == "heartbeat: New item"


def test_heartbeat_missing_file_graceful(tmp_path):
    """Missing HEARTBEAT.md should not crash."""
    sched = _make_scheduler(tmp_path)
    created = sched._check_heartbeat()
    assert created == []


def test_heartbeat_per_business(tmp_path):
    """Per-business HEARTBEAT.md files are also checked."""
    # Global heartbeat
    hb_global = tmp_path / "HEARTBEAT.md"
    hb_global.write_text("- [ ] Global task (daily)\n")

    # Business heartbeat
    biz_dir = tmp_path / "businesses" / "shop1"
    biz_dir.mkdir(parents=True)
    hb_biz = biz_dir / "HEARTBEAT.md"
    hb_biz.write_text("- [ ] Business task (weekly)\n")

    sched = _make_scheduler(tmp_path)
    created = sched._check_heartbeat()
    assert len(created) == 2
    names = {t["name"] for t in created}
    assert "heartbeat: Global task" in names
    assert "heartbeat: Business task" in names


def test_heartbeat_does_not_duplicate_existing_tasks(tmp_path):
    """If a heartbeat task already exists (pending/running), don't duplicate it."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("- [ ] Check email (every 30m)\n")
    sched = _make_scheduler(tmp_path)

    # First call creates task
    created1 = sched._check_heartbeat()
    assert len(created1) == 1

    # Force re-parse by bumping mtime
    time.sleep(0.05)
    hb.write_text("- [ ] Check email (every 30m)\n")

    # Second call should not duplicate
    created2 = sched._check_heartbeat()
    assert len(created2) == 0

    # Only one task in queue
    tasks = [t for t in sched.queue.list_tasks() if t["name"] == "heartbeat: Check email"]
    assert len(tasks) == 1


def test_heartbeat_called_from_tick(tmp_path):
    """tick() should call _check_heartbeat()."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("- [ ] Check email (every 30m)\n")
    sched = _make_scheduler(tmp_path)

    # tick() processes due tasks AND checks heartbeat
    sched.tick()

    # Heartbeat task should have been created
    tasks = sched.queue.list_tasks()
    assert any(t["name"] == "heartbeat: Check email" for t in tasks)


def test_heartbeat_payload_contains_source(tmp_path):
    """Heartbeat tasks should include source file info in payload."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("- [ ] Check email (every 30m)\n")
    sched = _make_scheduler(tmp_path)
    created = sched._check_heartbeat()
    assert len(created) == 1
    task = sched.queue.get_task(created[0]["id"])
    assert task["payload"]["source"] == str(hb)
    assert task["payload"]["schedule"] == "every 30m"


def test_heartbeat_schedule_to_cron_conversion(tmp_path):
    """Schedule strings should be converted to cron expressions for TaskQueue."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        "- [ ] Every 30m task (every 30m)\n"
        "- [ ] Hourly task (hourly)\n"
        "- [ ] Daily task (daily)\n"
        "- [ ] Weekly task (weekly)\n"
        "- [ ] Every 2h task (every 2h)\n"
    )
    sched = _make_scheduler(tmp_path)
    created = sched._check_heartbeat()
    assert len(created) == 5

    # Verify cron schedules were set
    for t in created:
        task = sched.queue.get_task(t["id"])
        assert task["schedule"] is not None, f"Task {task['name']} missing schedule"

    # Check specific conversions
    tasks_by_name = {
        sched.queue.get_task(t["id"])["name"]: sched.queue.get_task(t["id"])
        for t in created
    }
    assert tasks_by_name["heartbeat: Every 30m task"]["schedule"] == "*/30 * * * *"
    assert tasks_by_name["heartbeat: Hourly task"]["schedule"] == "0 * * * *"
    assert tasks_by_name["heartbeat: Daily task"]["schedule"] == "0 0 * * *"
    assert tasks_by_name["heartbeat: Weekly task"]["schedule"] == "0 0 * * 0"
    assert tasks_by_name["heartbeat: Every 2h task"]["schedule"] == "0 */2 * * *"
