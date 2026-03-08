# src/merkaba/orchestration/scheduler.py
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from merkaba.orchestration.heartbeat_checklist import parse_heartbeat_md
from merkaba.orchestration.queue import TaskQueue

logger = logging.getLogger(__name__)

# Circuit breaker: pause a task after this many consecutive failures.
MAX_CONSECUTIVE_FAILURES = 5

# Convert human-readable schedule strings to cron expressions.
_SCHEDULE_MAP = {
    "hourly": "0 * * * *",
    "daily": "0 0 * * *",
    "weekly": "0 0 * * 0",
}

# Matches: "every 30m", "every 2h", "every 1h"
_EVERY_RE = re.compile(r"every\s+(\d+)\s*([mh])", re.IGNORECASE)


def _schedule_to_cron(schedule: str) -> str | None:
    """Convert a heartbeat schedule string to a cron expression.

    Supports: "every 30m", "every 2h", "hourly", "daily", "weekly".
    Returns None if unrecognised.
    """
    normalised = schedule.strip().lower()
    if normalised in _SCHEDULE_MAP:
        return _SCHEDULE_MAP[normalised]

    m = _EVERY_RE.match(normalised)
    if m:
        value, unit = int(m.group(1)), m.group(2).lower()
        if unit == "m":
            return f"*/{value} * * * *"
        if unit == "h":
            return f"0 */{value} * * *"

    logger.warning("Unrecognised heartbeat schedule: %r", schedule)
    return None


@dataclass
class Scheduler:
    """Task scheduler daemon. Finds due tasks and dispatches them."""

    queue: TaskQueue
    on_task_due: Callable[[dict], dict] | None = None
    merkaba_home: Path | None = None

    # Internal state for mtime tracking: path -> mtime
    _heartbeat_mtimes: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    # Track which heartbeat task names already exist (to avoid duplicates)
    _known_heartbeat_names: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self):
        if self.merkaba_home is None:
            from merkaba.paths import merkaba_home as _merkaba_home
            self.merkaba_home = Path(_merkaba_home())
        else:
            self.merkaba_home = Path(self.merkaba_home)
        # Seed known heartbeat names from existing tasks in the queue
        self._seed_known_heartbeat_names()

    def _seed_known_heartbeat_names(self) -> None:
        """Load existing heartbeat task names so we don't duplicate on restart."""
        try:
            for task in self.queue.list_tasks():
                if task.get("task_type") == "heartbeat" and task["status"] in (
                    "pending",
                    "running",
                ):
                    self._known_heartbeat_names.add(task["name"])
        except Exception:
            pass  # Graceful on empty/corrupt DB

    def tick(self) -> list[dict[str, Any]]:
        """One scheduler cycle: find due tasks, execute them, log results.

        Also checks HEARTBEAT.md files for new items to schedule.

        Note: there is a minor race between start_run() changing the task
        status and compute_next_run() reading the task back.  This is
        acceptable for a single-process scheduler; a multi-process design
        would need row-level locking or an atomic compare-and-swap.
        """
        # Check heartbeat files for new items
        self._check_heartbeat()

        due = self.queue.get_due_tasks()
        for task in due:
            run_id = self.queue.start_run(task["id"])
            try:
                result = self._dispatch(task)
                self.queue.finish_run(run_id, "success", result=result)
            except Exception as e:
                logger.error("Task %s failed: %s", task["id"], e)
                self.queue.finish_run(run_id, "failed", error=str(e))
                self._check_circuit_breaker(task["id"])
            self.queue.compute_next_run(task["id"])
        return due

    def _check_circuit_breaker(self, task_id: int) -> None:
        """Pause task if it has too many consecutive failures."""
        runs = self.queue.get_runs(task_id)
        # Only consider the most recent MAX_CONSECUTIVE_FAILURES runs
        recent = runs[:MAX_CONSECUTIVE_FAILURES]
        if len(recent) >= MAX_CONSECUTIVE_FAILURES:
            if all(r["status"] == "failed" for r in recent):
                logger.warning(
                    "Task %d has %d consecutive failures — pausing",
                    task_id, MAX_CONSECUTIVE_FAILURES,
                )
                self.queue.pause_task(task_id)

    def _check_heartbeat(self) -> list[dict[str, Any]]:
        """Check global and per-business HEARTBEAT.md files for due items.

        Uses file mtime tracking to avoid re-parsing unchanged files.
        Returns list of newly created task dicts.
        """
        created: list[dict[str, Any]] = []

        # Collect heartbeat file paths to check
        paths: list[Path] = []

        # Global heartbeat
        global_hb = self.merkaba_home / "HEARTBEAT.md"
        paths.append(global_hb)

        # Per-business heartbeats
        biz_root = self.merkaba_home / "businesses"
        if biz_root.is_dir():
            for biz_dir in sorted(biz_root.iterdir()):
                if biz_dir.is_dir():
                    paths.append(biz_dir / "HEARTBEAT.md")

        for path in paths:
            created.extend(self._process_heartbeat_file(path))

        return created

    def _process_heartbeat_file(self, path: Path) -> list[dict[str, Any]]:
        """Parse a single HEARTBEAT.md if changed, create tasks for due items."""
        created: list[dict[str, Any]] = []

        # Check mtime — skip if unchanged
        try:
            current_mtime = path.stat().st_mtime
        except (FileNotFoundError, OSError):
            return created

        key = str(path)
        last_mtime = self._heartbeat_mtimes.get(key, 0.0)
        if current_mtime <= last_mtime:
            return created

        # File changed — re-parse
        self._heartbeat_mtimes[key] = current_mtime
        items = parse_heartbeat_md(path)

        for item in items:
            # Skip checked (done) items and items without schedules
            if item.checked or not item.schedule:
                continue

            task_name = f"heartbeat: {item.description}"

            # Skip if task already exists
            if task_name in self._known_heartbeat_names:
                continue

            cron = _schedule_to_cron(item.schedule)
            if cron is None:
                continue

            task_id = self.queue.add_task(
                name=task_name,
                task_type="heartbeat",
                schedule=cron,
                payload={
                    "source": str(path),
                    "description": item.description,
                    "schedule": item.schedule,
                },
            )
            self._known_heartbeat_names.add(task_name)
            task = self.queue.get_task(task_id)
            created.append(task)
            logger.info("Created heartbeat task: %s (schedule: %s)", task_name, cron)

        return created

    def run_loop(self, interval: int = 60) -> None:
        """Run tick() in a loop every `interval` seconds."""
        logger.info("Scheduler starting (interval=%ds)", interval)
        try:
            while True:
                try:
                    due = self.tick()
                    if due:
                        logger.info("Processed %d due tasks", len(due))
                except Exception as e:
                    logger.error("Scheduler tick error: %s", e)
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped")

    def _dispatch(self, task: dict) -> dict:
        """Call on_task_due callback, or default stub."""
        if self.on_task_due:
            return self.on_task_due(task)
        logger.info("Stub dispatch for task %s (%s)", task["id"], task["name"])
        return {"status": "stub", "message": f"Task {task['name']} dispatched (no handler)"}
