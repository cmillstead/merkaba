# src/merkaba/observability/audit.py
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DecisionAuditStore:
    """SQLite-backed decision audit trail."""

    db_path: str = field(default_factory=lambda: os.path.expanduser("~/.merkaba/memory.db"))
    _conn: sqlite3.Connection = field(default=None, init=False, repr=False)

    def __post_init__(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS decision_audit (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                alternatives TEXT,
                context_summary TEXT,
                model TEXT,
                confidence REAL,
                timestamp TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def record(
        self,
        decision_type: str,
        decision: str,
        alternatives: list[str] | None = None,
        context_summary: str | None = None,
        model: str | None = None,
        confidence: float | None = None,
        trace_id: str = "no-trace",
    ) -> str:
        """Record a decision. Returns the record ID."""
        record_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """INSERT INTO decision_audit
               (id, trace_id, decision_type, decision, alternatives,
                context_summary, model, confidence, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record_id, trace_id, decision_type, decision,
             json.dumps(alternatives) if alternatives else None,
             context_summary, model, confidence, now),
        )
        self._conn.commit()
        return record_id

    def get_by_trace(self, trace_id: str) -> list[dict]:
        """Get all decisions for a given trace ID."""
        rows = self._conn.execute(
            "SELECT * FROM decision_audit WHERE trace_id = ? ORDER BY timestamp",
            (trace_id,),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            if d.get("alternatives"):
                d["alternatives"] = json.loads(d["alternatives"])
            results.append(d)
        return results

    def get_recent(
        self,
        decision_type: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get recent decisions, optionally filtered by type."""
        if decision_type:
            rows = self._conn.execute(
                "SELECT * FROM decision_audit WHERE decision_type = ? ORDER BY timestamp DESC LIMIT ?",
                (decision_type, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM decision_audit ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            if d.get("alternatives"):
                d["alternatives"] = json.loads(d["alternatives"])
            results.append(d)
        return results

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# Module-level lazy singleton
_singleton: DecisionAuditStore | None = None


def get_audit_store() -> DecisionAuditStore | None:
    """Get or create the module-level DecisionAuditStore singleton."""
    global _singleton
    if _singleton is None:
        try:
            _singleton = DecisionAuditStore()
        except Exception:
            return None
    return _singleton


def record_decision(
    decision_type: str,
    decision: str,
    alternatives: list[str] | None = None,
    context_summary: str | None = None,
    model: str | None = None,
    confidence: float | None = None,
    trace_id: str | None = None,
) -> None:
    """Fire-and-forget decision recording. Never raises."""
    try:
        store = get_audit_store()
        if store is None:
            return
        if trace_id is None:
            from merkaba.observability.tracing import get_trace_id
            trace_id = get_trace_id()
        store.record(
            decision_type=decision_type,
            decision=decision,
            alternatives=alternatives,
            context_summary=context_summary,
            model=model,
            confidence=confidence,
            trace_id=trace_id,
        )
    except Exception:
        pass
