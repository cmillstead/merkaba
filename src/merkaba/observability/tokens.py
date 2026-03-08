# src/merkaba/observability/tokens.py
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from merkaba.paths import db_path as _db_path


_SAFE_COLUMNS = {"model": "model", "worker_type": "worker_type"}


@dataclass
class TokenUsageStore:
    """SQLite-backed token usage tracking."""

    db_path: str = field(default_factory=lambda: _db_path("memory"))
    _conn: sqlite3.Connection = field(default=None, init=False, repr=False)

    def __post_init__(self):
        from merkaba.db import create_connection

        self._conn = create_connection(self.db_path, foreign_keys=False)
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                model TEXT NOT NULL,
                worker_type TEXT,
                task_id TEXT,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def record(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_ms: int = 0,
        trace_id: str = "no-trace",
        worker_type: str | None = None,
        task_id: str | None = None,
    ) -> str:
        """Record a token usage event. Returns the record ID."""
        record_id = uuid.uuid4().hex[:12]
        total_tokens = input_tokens + output_tokens
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        self._conn.execute(
            """INSERT INTO token_usage
               (id, trace_id, model, worker_type, task_id,
                input_tokens, output_tokens, total_tokens, duration_ms, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, trace_id, model, worker_type, task_id,
             input_tokens, output_tokens, total_tokens, duration_ms, now),
        )
        self._conn.commit()
        return record_id

    def get_summary(self, group_by: str = "model", days: int = 7) -> list[dict]:
        """Get aggregated token usage stats.

        Args:
            group_by: Column to group by — "model" or "worker_type".
            days: Number of days to look back.
        """
        col = _SAFE_COLUMNS.get(group_by, "model")

        rows = self._conn.execute(
            f"""SELECT {col},
                       COUNT(*) as call_count,
                       SUM(input_tokens) as total_input,
                       SUM(output_tokens) as total_output,
                       SUM(total_tokens) as total_tokens,
                       SUM(duration_ms) as total_duration_ms
                FROM token_usage
                WHERE timestamp >= datetime('now', ?)
                GROUP BY {col}
                ORDER BY total_tokens DESC""",
            (f"-{days} days",),
        ).fetchall()

        return [dict(row) for row in rows]

    def get_by_trace(self, trace_id: str) -> list[dict]:
        """Get all token usage records for a given trace ID."""
        rows = self._conn.execute(
            "SELECT * FROM token_usage WHERE trace_id = ? ORDER BY timestamp",
            (trace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# Module-level lazy singleton
_singleton: TokenUsageStore | None = None


def get_token_store() -> TokenUsageStore | None:
    """Get or create the module-level TokenUsageStore singleton."""
    global _singleton
    if _singleton is None:
        try:
            _singleton = TokenUsageStore()
        except Exception:
            return None
    return _singleton
