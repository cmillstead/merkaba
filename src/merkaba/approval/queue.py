# src/merkaba/approval/queue.py
import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class ActionQueue:
    """SQLite-backed approval queue for pending actions."""

    db_path: str = field(
        default_factory=lambda: os.path.expanduser("~/.merkaba/actions.db")
    )
    _conn: sqlite3.Connection = field(default=None, init=False, repr=False)

    def __post_init__(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._create_tables()

    def _create_tables(self):
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                task_run_id INTEGER,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                params TEXT,
                autonomy_level INTEGER NOT NULL DEFAULT 1,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,
                executed_at TEXT,
                result TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                approved_count INTEGER DEFAULT 0,
                denied_count INTEGER DEFAULT 0,
                last_updated TEXT NOT NULL,
                UNIQUE(business_id, action_type)
            )
        """)
        self._conn.commit()

    def _now(self) -> str:
        return datetime.now().isoformat()

    # --- Action CRUD ---

    def add_action(
        self,
        business_id: int,
        action_type: str,
        description: str,
        params: dict | None = None,
        autonomy_level: int = 1,
        task_run_id: int | None = None,
    ) -> int:
        autonomy_level = max(1, min(5, autonomy_level))
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO actions
               (business_id, task_run_id, action_type, description,
                params, autonomy_level, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (
                business_id,
                task_run_id,
                action_type,
                description,
                json.dumps(params) if params else None,
                autonomy_level,
                self._now(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_action(self, action_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM actions WHERE id = ?", (action_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def list_actions(
        self,
        status: str | None = None,
        business_id: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM actions WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if business_id is not None:
            query += " AND business_id = ?"
            params.append(business_id)
        query += " ORDER BY created_at DESC"
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def decide(
        self,
        action_id: int,
        approved: bool,
        decided_by: str = "cli",
    ) -> dict[str, Any] | None:
        action = self.get_action(action_id)
        if not action or action["status"] != "pending":
            return None

        status = "approved" if approved else "denied"
        now = self._now()
        self._conn.execute(
            "UPDATE actions SET status = ?, decided_at = ?, decided_by = ? WHERE id = ?",
            (status, now, decided_by, action_id),
        )
        self._conn.commit()
        self._update_stats(action["business_id"], action["action_type"], approved)
        return self.get_action(action_id)

    def mark_executed(self, action_id: int, result: dict | None = None) -> None:
        self._conn.execute(
            "UPDATE actions SET status = 'executed', executed_at = ?, result = ? WHERE id = ?",
            (self._now(), json.dumps(result) if result else None, action_id),
        )
        self._conn.commit()

    def mark_failed(self, action_id: int, result: dict | None = None) -> None:
        self._conn.execute(
            "UPDATE actions SET status = 'failed', executed_at = ?, result = ? WHERE id = ?",
            (self._now(), json.dumps(result) if result else None, action_id),
        )
        self._conn.commit()

    def get_pending_count(self, business_id: int | None = None) -> int:
        query = "SELECT COUNT(*) FROM actions WHERE status = 'pending'"
        params: list[Any] = []
        if business_id is not None:
            query += " AND business_id = ?"
            params.append(business_id)
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()[0]

    def count_recent_approvals(self, window_seconds: int = 60) -> int:
        """Count approvals within the given time window."""
        cutoff = (datetime.now() - timedelta(seconds=window_seconds)).isoformat()
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM actions WHERE status = 'approved' AND decided_at >= ?",
            (cutoff,),
        )
        return cursor.fetchone()[0]

    # --- Stats for graduation ---

    def _update_stats(self, business_id: int, action_type: str, approved: bool) -> None:
        col = "approved_count" if approved else "denied_count"
        if col not in ("approved_count", "denied_count"):
            return
        now = self._now()
        self._conn.execute(
            f"""INSERT INTO approval_stats (business_id, action_type, {col}, last_updated)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(business_id, action_type)
                DO UPDATE SET {col} = {col} + 1, last_updated = ?""",
            (business_id, action_type, now, now),
        )
        self._conn.commit()

    def get_stats(
        self, business_id: int, action_type: str | None = None
    ) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        if action_type:
            cursor.execute(
                "SELECT * FROM approval_stats WHERE business_id = ? AND action_type = ?",
                (business_id, action_type),
            )
        else:
            cursor.execute(
                "SELECT * FROM approval_stats WHERE business_id = ? ORDER BY action_type",
                (business_id,),
            )
        return [dict(row) for row in cursor.fetchall()]

    # --- Helpers ---

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if d.get("params"):
            d["params"] = json.loads(d["params"])
        if d.get("result"):
            d["result"] = json.loads(d["result"])
        return d

    def stats(self) -> dict[str, int]:
        cursor = self._conn.cursor()
        counts = {}
        cursor.execute("SELECT COUNT(*) FROM actions")
        counts["total"] = cursor.fetchone()[0]
        cursor.execute("SELECT status, COUNT(*) FROM actions GROUP BY status")
        for row in cursor.fetchall():
            counts[row[0]] = row[1]
        return counts

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
