# src/merkaba/orchestration/queue.py
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from croniter import croniter
from merkaba.paths import db_path as _db_path

logger = logging.getLogger(__name__)


@dataclass
class TaskQueue:
    """SQLite-backed task queue for scheduled and one-shot tasks."""

    MAX_TASK_FAILURES = 3

    db_path: str = field(default_factory=lambda: _db_path("tasks"))
    _conn: sqlite3.Connection = field(default=None, init=False, repr=False)

    def __post_init__(self):
        from merkaba.security.file_permissions import ensure_secure_permissions
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            ensure_secure_permissions(db_dir)
        self._conn = sqlite3.connect(self.db_path)
        ensure_secure_permissions(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._create_tables()

    def _create_tables(self):
        cursor = self._conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER,
                name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                schedule TEXT,
                next_run TEXT,
                last_run TEXT,
                status TEXT DEFAULT 'pending',
                payload TEXT,
                autonomy_level INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                result TEXT,
                error TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)

        # Idempotent schema migrations for failure tracking
        for col, typedef in [("failure_count", "INTEGER DEFAULT 0"), ("last_error", "TEXT")]:
            try:
                cursor.execute(f"ALTER TABLE task_runs ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                logger.debug("Column %s already exists in task_runs", col)

        # Indexes for common query patterns
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status_next_run
            ON tasks(status, next_run)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_task_type
            ON tasks(task_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_runs_task_id
            ON task_runs(task_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_runs_status
            ON task_runs(status)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                original_run_id INTEGER,
                failure_count INTEGER NOT NULL,
                last_error TEXT,
                context_snapshot TEXT,
                created_at TEXT NOT NULL,
                resolved INTEGER DEFAULT 0,
                resolution_notes TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)

        self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # --- Task CRUD ---

    def add_task(
        self,
        name: str,
        task_type: str,
        schedule: str | None = None,
        business_id: int | None = None,
        payload: dict | None = None,
        autonomy_level: int = 1,
    ) -> int:
        now = self._now()
        next_run = None
        if schedule:
            next_run = croniter(schedule, datetime.now(timezone.utc)).get_next(datetime).replace(tzinfo=None).isoformat()

        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO tasks
               (business_id, name, task_type, schedule, next_run, status, payload, autonomy_level, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
            (
                business_id,
                name,
                task_type,
                schedule,
                next_run,
                json.dumps(payload) if payload else None,
                autonomy_level,
                now,
                now,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        if d["payload"]:
            d["payload"] = json.loads(d["payload"])
        return d

    def list_tasks(
        self,
        status: str | None = None,
        business_id: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if business_id is not None:
            query += " AND business_id = ?"
            params.append(business_id)
        query += " ORDER BY created_at"

        cursor = self._conn.cursor()
        cursor.execute(query, params)
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            if d["payload"]:
                d["payload"] = json.loads(d["payload"])
            rows.append(d)
        return rows

    def update_task(self, task_id: int, **kwargs) -> None:
        allowed = {"name", "task_type", "schedule", "next_run", "last_run", "status", "payload", "autonomy_level", "business_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        if "payload" in updates and isinstance(updates["payload"], dict):
            updates["payload"] = json.dumps(updates["payload"])
        updates["updated_at"] = self._now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        self._conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        self._conn.commit()

    def delete_task(self, task_id: int) -> bool:
        """Permanently delete a task and its runs.

        Returns True if the task existed and was deleted, False if not found.
        All three DELETEs are wrapped in an explicit transaction so the
        operation is atomic — either everything is removed or nothing is.
        """
        task = self.get_task(task_id)
        if not task:
            return False
        self._conn.execute("BEGIN")
        try:
            self._conn.execute("DELETE FROM task_runs WHERE task_id = ?", (task_id,))
            self._conn.execute("DELETE FROM dead_letter_queue WHERE task_id = ?", (task_id,))
            cursor = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn.execute("COMMIT")
            return cursor.rowcount > 0
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def pause_task(self, task_id: int) -> None:
        self.update_task(task_id, status="paused")

    def resume_task(self, task_id: int) -> None:
        task = self.get_task(task_id)
        if not task:
            return
        updates: dict[str, Any] = {"status": "pending"}
        if task["schedule"]:
            updates["next_run"] = croniter(task["schedule"], datetime.now(timezone.utc)).get_next(datetime).replace(tzinfo=None).isoformat()
        self.update_task(task_id, **updates)

    # --- Due task detection ---

    def get_due_tasks(self) -> list[dict[str, Any]]:
        now = self._now()
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE status = 'pending' AND next_run IS NOT NULL AND next_run <= ? ORDER BY next_run",
            (now,),
        )
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            if d["payload"]:
                d["payload"] = json.loads(d["payload"])
            rows.append(d)
        return rows

    def compute_next_run(self, task_id: int) -> str | None:
        task = self.get_task(task_id)
        if not task or not task["schedule"]:
            return None
        next_run = croniter(task["schedule"], datetime.now(timezone.utc)).get_next(datetime).replace(tzinfo=None).isoformat()
        self.update_task(task_id, next_run=next_run, last_run=self._now())
        return next_run

    # --- Run tracking ---

    def start_run(self, task_id: int) -> int:
        self.update_task(task_id, status="running")
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO task_runs (task_id, started_at, status) VALUES (?, ?, 'running')",
            (task_id, self._now()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE task_runs SET finished_at = ?, status = ?, result = ?, error = ? WHERE id = ?",
            (
                self._now(),
                status,
                json.dumps(result) if result else None,
                error,
                run_id,
            ),
        )
        # Get task_id from run and update task status
        cursor = self._conn.cursor()
        cursor.execute("SELECT task_id FROM task_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        if row:
            if status == "failed":
                self.record_failure(run_id, row["task_id"], error)
            else:
                self.update_task(row["task_id"], status="pending")
        self._conn.commit()

    def get_runs(self, task_id: int) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM task_runs WHERE task_id = ? ORDER BY started_at DESC",
            (task_id,),
        )
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            if d["result"]:
                d["result"] = json.loads(d["result"])
            rows.append(d)
        return rows

    def get_runs_for_tasks(
        self,
        task_ids: list[int],
        limit_per_task: int = 5,
    ) -> dict[int, list[dict[str, Any]]]:
        """Batch-fetch recent runs for multiple tasks in a single query.

        Returns a dict mapping each task_id to its list of runs (most recent
        first), capped at ``limit_per_task`` per task.  Uses a window function
        so only one round-trip to the database is needed regardless of how many
        task_ids are provided.
        """
        if not task_ids:
            return {}

        placeholders = ",".join("?" for _ in task_ids)
        cursor = self._conn.cursor()
        cursor.execute(
            f"""SELECT * FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY task_id ORDER BY started_at DESC
                           ) AS rn
                    FROM task_runs
                    WHERE task_id IN ({placeholders})
                ) sub
                WHERE rn <= ?
                ORDER BY task_id, started_at DESC""",
            (*task_ids, limit_per_task),
        )

        result: dict[int, list[dict[str, Any]]] = {tid: [] for tid in task_ids}
        for row in cursor.fetchall():
            d = dict(row)
            d.pop("rn", None)  # Remove the window-function helper column
            if d.get("result"):
                try:
                    d["result"] = json.loads(d["result"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.setdefault(d["task_id"], []).append(d)
        return result

    # --- Dead letter queue ---

    def record_failure(self, run_id: int, task_id: int, error: str | None) -> None:
        """Record a task failure and move to DLQ if threshold exceeded."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM task_runs WHERE task_id = ? AND status = 'failed'",
            (task_id,),
        )
        failure_count = cursor.fetchone()[0]

        if failure_count >= self.MAX_TASK_FAILURES:
            self._move_to_dead_letter(task_id, run_id, failure_count, error)
            self.update_task(task_id, status="dead_letter")
            logger.warning("Task %d moved to dead letter queue after %d failures", task_id, failure_count)
        else:
            self.update_task(task_id, status="failed")

    def _move_to_dead_letter(self, task_id: int, run_id: int, failure_count: int, error: str | None) -> None:
        task = self.get_task(task_id)
        context = json.dumps(task) if task else None
        self._conn.execute(
            """INSERT INTO dead_letter_queue
               (task_id, original_run_id, failure_count, last_error, context_snapshot, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, run_id, failure_count, error, context, self._now()),
        )
        self._conn.commit()

    def list_dead_letters(self, resolved: bool = False) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM dead_letter_queue WHERE resolved = ? ORDER BY created_at DESC",
            (1 if resolved else 0,),
        )
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            if d.get("context_snapshot"):
                try:
                    d["context_snapshot"] = json.loads(d["context_snapshot"])
                except (json.JSONDecodeError, TypeError):
                    pass
            rows.append(d)
        return rows

    def resolve_dead_letter(self, dlq_id: int, notes: str | None = None) -> None:
        self._conn.execute(
            "UPDATE dead_letter_queue SET resolved = 1, resolution_notes = ? WHERE id = ?",
            (notes, dlq_id),
        )
        self._conn.commit()

    # --- Aggregate Queries ---

    def get_recent_runs(
        self,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return recent task runs, optionally filtered by status.

        Joins with the tasks table to include task name and task_type.
        Returns plain dicts (not Row objects) for JSON serialization.
        """
        cursor = self._conn.cursor()
        if status:
            cursor.execute(
                """SELECT tr.id, tr.task_id, tr.started_at, tr.finished_at,
                          tr.status, tr.result, tr.error,
                          t.name, t.task_type
                   FROM task_runs tr
                   LEFT JOIN tasks t ON tr.task_id = t.id
                   WHERE tr.status = ?
                   ORDER BY tr.started_at DESC
                   LIMIT ?""",
                (status, limit),
            )
        else:
            cursor.execute(
                """SELECT tr.id, tr.task_id, tr.started_at, tr.finished_at,
                          tr.status, tr.result, tr.error,
                          t.name, t.task_type
                   FROM task_runs tr
                   LEFT JOIN tasks t ON tr.task_id = t.id
                   ORDER BY tr.started_at DESC
                   LIMIT ?""",
                (limit,),
            )
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            if d.get("result"):
                try:
                    d["result"] = json.loads(d["result"])
                except (json.JSONDecodeError, TypeError):
                    pass
            rows.append(d)
        return rows

    def count_by_status(self) -> dict[str, int]:
        """Return a dict mapping each task status to its count.

        Example: {"pending": 3, "running": 1, "failed": 0, "dead_letter": 0}
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        return {row[0]: row[1] for row in cursor.fetchall()}

    # --- Stats ---

    def stats(self) -> dict[str, int]:
        cursor = self._conn.cursor()
        counts = {}
        allowed_tables = {"tasks", "task_runs"}
        for table in ("tasks", "task_runs"):
            if table not in allowed_tables:
                continue
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        # Status breakdown
        cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        for row in cursor.fetchall():
            counts[f"tasks_{row[0]}"] = row[1]
        return counts

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
