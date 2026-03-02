# src/merkaba/memory/store.py
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryStore:
    """SQLite-backed structured memory for Merkaba."""

    db_path: str = field(default_factory=lambda: os.path.expanduser("~/.merkaba/memory.db"))
    contradiction_detector: Any = field(default=None, repr=False)
    _conn: sqlite3.Connection = field(default=None, init=False, repr=False)

    def __post_init__(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._create_tables()

    def _create_tables(self):
        cursor = self._conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                autonomy_level INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence INTEGER DEFAULT 100,
                source TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (business_id) REFERENCES businesses(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                outcome TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (business_id) REFERENCES businesses(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                related_entity TEXT NOT NULL,
                metadata TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (business_id) REFERENCES businesses(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (business_id) REFERENCES businesses(id),
                UNIQUE(business_id, entity_type, entity_id, key)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_business_id INTEGER,
                category TEXT NOT NULL,
                insight TEXT NOT NULL,
                evidence TEXT,
                confidence INTEGER DEFAULT 50,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER,
                task_type TEXT,
                task_id INTEGER,
                summary TEXT,
                outcome TEXT,
                outcome_details TEXT,
                key_decisions TEXT,
                duration_seconds INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tags TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_business_type
            ON episodes(business_id, task_type, created_at)
        """)

        # Indexes for common query patterns on relationships and state tables.
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_entity
            ON relationships(business_id, entity_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_related
            ON relationships(business_id, related_entity)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_state_business_type
            ON state(business_id, entity_type)
        """)

        self._conn.commit()
        self._run_migrations()

    def _run_migrations(self):
        """Add lifecycle columns to existing tables (safe to re-run)."""
        migrations = []
        for table in ("facts", "decisions", "learnings"):
            migrations.extend([
                f"ALTER TABLE {table} ADD COLUMN relevance_score REAL DEFAULT 1.0",
                f"ALTER TABLE {table} ADD COLUMN last_accessed TEXT",
                f"ALTER TABLE {table} ADD COLUMN access_count INTEGER DEFAULT 0",
                f"ALTER TABLE {table} ADD COLUMN archived INTEGER DEFAULT 0",
            ])
        for sql in migrations:
            try:
                self._conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Indexes on archived column (must run after migration adds the column).
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_facts_business_archived
            ON facts(business_id, archived)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_business_archived
            ON decisions(business_id, archived)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_learnings_archived
            ON learnings(archived)
        """)
        self._conn.commit()

    def _now(self) -> str:
        return datetime.now().isoformat()

    # --- Business CRUD ---

    def add_business(self, name: str, type: str, autonomy_level: int = 1) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO businesses (name, type, autonomy_level, created_at) VALUES (?, ?, ?, ?)",
            (name, type, autonomy_level, self._now()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_business(self, business_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM businesses WHERE id = ?", (business_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_businesses(self) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM businesses ORDER BY created_at")
        return [dict(row) for row in cursor.fetchall()]

    def update_business(self, business_id: int, **kwargs) -> None:
        allowed = {"name", "type", "autonomy_level"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [business_id]
        self._conn.execute(
            f"UPDATE businesses SET {set_clause} WHERE id = ?", values
        )
        self._conn.commit()

    # --- Facts CRUD ---

    def add_fact(
        self,
        business_id: int,
        category: str,
        key: str,
        value: str,
        confidence: int = 100,
        source: str | None = None,
        check_contradictions: bool = False,
    ) -> int:
        # Check for contradictions before inserting
        if check_contradictions and self.contradiction_detector:
            try:
                contradicted = self.contradiction_detector.check_on_write(
                    business_id, category, key, value
                )
                if contradicted:
                    self.contradiction_detector.resolve([c["id"] for c in contradicted])
                    logger.info(
                        "Archived %d contradicted facts for business %d",
                        len(contradicted), business_id,
                    )
            except Exception as e:
                logger.warning("Contradiction check failed: %s", e)

        now = self._now()
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO facts (business_id, category, key, value, confidence, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (business_id, category, key, value, confidence, source, now, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_fact(self, fact_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM facts WHERE id = ?", (fact_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_facts(
        self, business_id: int, category: str | None = None, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        archive_filter = "" if include_archived else " AND archived = 0"
        if category:
            cursor.execute(
                f"SELECT * FROM facts WHERE business_id = ? AND category = ?{archive_filter} ORDER BY updated_at DESC",
                (business_id, category),
            )
        else:
            cursor.execute(
                f"SELECT * FROM facts WHERE business_id = ?{archive_filter} ORDER BY updated_at DESC",
                (business_id,),
            )
        return [dict(row) for row in cursor.fetchall()]

    def update_fact(self, fact_id: int, **kwargs) -> None:
        allowed = {"value", "confidence", "source", "category", "key"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        updates["updated_at"] = self._now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [fact_id]
        self._conn.execute(f"UPDATE facts SET {set_clause} WHERE id = ?", values)
        self._conn.commit()

    # --- Decisions CRUD ---

    def add_decision(
        self,
        business_id: int,
        action_type: str,
        decision: str,
        reasoning: str,
    ) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO decisions (business_id, action_type, decision, reasoning, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (business_id, action_type, decision, reasoning, self._now()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_decision(self, decision_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_decisions(
        self, business_id: int, action_type: str | None = None, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        archive_filter = "" if include_archived else " AND archived = 0"
        if action_type:
            cursor.execute(
                f"SELECT * FROM decisions WHERE business_id = ? AND action_type = ?{archive_filter} ORDER BY created_at DESC",
                (business_id, action_type),
            )
        else:
            cursor.execute(
                f"SELECT * FROM decisions WHERE business_id = ?{archive_filter} ORDER BY created_at DESC",
                (business_id,),
            )
        return [dict(row) for row in cursor.fetchall()]

    def update_decision_outcome(self, decision_id: int, outcome: str) -> None:
        self._conn.execute(
            "UPDATE decisions SET outcome = ? WHERE id = ?",
            (outcome, decision_id),
        )
        self._conn.commit()

    # --- Relationships CRUD ---

    def add_relationship(
        self,
        business_id: int,
        entity_type: str,
        entity_id: str,
        relation: str,
        related_entity: str,
        metadata: dict | None = None,
    ) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO relationships (business_id, entity_type, entity_id, relation, related_entity, metadata, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                business_id,
                entity_type,
                entity_id,
                relation,
                related_entity,
                json.dumps(metadata) if metadata else None,
                self._now(),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_relationships(
        self, business_id: int, entity_type: str | None = None
    ) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        if entity_type:
            cursor.execute(
                "SELECT * FROM relationships WHERE business_id = ? AND entity_type = ? ORDER BY updated_at DESC",
                (business_id, entity_type),
            )
        else:
            cursor.execute(
                "SELECT * FROM relationships WHERE business_id = ? ORDER BY updated_at DESC",
                (business_id,),
            )
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            if d["metadata"]:
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            rows.append(d)
        return rows

    # --- Traversal ---

    def traverse(
        self, entity: str, depth: int = 2, business_id: int | None = None
    ) -> list[dict[str, Any]]:
        """BFS traversal over relationships table starting from entity.

        Follows edges bidirectionally up to depth hops.
        Returns flat list of relationship dicts encountered.
        """
        visited_entities: set[str] = {entity.lower()}
        result: list[dict[str, Any]] = []
        frontier: set[str] = {entity}

        for _ in range(depth):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for current in frontier:
                rels = self._get_edges(current, business_id)
                for rel in rels:
                    if rel["entity_id"].lower() == current.lower():
                        other = rel["related_entity"]
                    else:
                        other = rel["entity_id"]

                    result.append(rel)
                    if other.lower() not in visited_entities:
                        visited_entities.add(other.lower())
                        next_frontier.add(other)
            frontier = next_frontier

        return result

    def _get_edges(
        self, entity: str, business_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Get all relationships where entity appears as either endpoint."""
        cursor = self._conn.cursor()
        if business_id is not None:
            cursor.execute(
                "SELECT * FROM relationships WHERE business_id = ? AND (entity_id = ? COLLATE NOCASE OR related_entity = ? COLLATE NOCASE)",
                (business_id, entity, entity),
            )
        else:
            cursor.execute(
                "SELECT * FROM relationships WHERE entity_id = ? COLLATE NOCASE OR related_entity = ? COLLATE NOCASE",
                (entity, entity),
            )
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            if d["metadata"]:
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            rows.append(d)
        return rows

    def find_entities(
        self, query: str, business_id: int | None = None
    ) -> list[str]:
        """Find known entity names that appear as substrings in the query."""
        cursor = self._conn.cursor()
        if business_id is not None:
            cursor.execute(
                "SELECT DISTINCT entity_id FROM relationships WHERE business_id = ? "
                "UNION SELECT DISTINCT related_entity FROM relationships WHERE business_id = ?",
                (business_id, business_id),
            )
        else:
            cursor.execute(
                "SELECT DISTINCT entity_id FROM relationships "
                "UNION SELECT DISTINCT related_entity FROM relationships"
            )
        all_entities = [row[0] for row in cursor.fetchall()]

        query_lower = query.lower()
        return [e for e in all_entities if e.lower() in query_lower]

    # --- State CRUD ---

    def set_state(
        self,
        business_id: int,
        entity_type: str,
        entity_id: str,
        key: str,
        value: str,
    ) -> None:
        self._conn.execute(
            """INSERT INTO state (business_id, entity_type, entity_id, key, value, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(business_id, entity_type, entity_id, key)
               DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (business_id, entity_type, entity_id, key, value, self._now()),
        )
        self._conn.commit()

    def get_state(
        self,
        business_id: int,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        query = "SELECT * FROM state WHERE business_id = ?"
        params: list[Any] = [business_id]
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        query += " ORDER BY updated_at DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # --- Learnings CRUD ---

    def add_learning(
        self,
        category: str,
        insight: str,
        evidence: str | None = None,
        confidence: int = 50,
        source_business_id: int | None = None,
    ) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO learnings (source_business_id, category, insight, evidence, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source_business_id, category, insight, evidence, confidence, self._now()),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_learning(self, learning_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM learnings WHERE id = ?", (learning_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_learnings(self, category: str | None = None, include_archived: bool = False) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        archive_filter = " WHERE archived = 0" if not include_archived else ""
        if category:
            if include_archived:
                cursor.execute(
                    "SELECT * FROM learnings WHERE category = ? ORDER BY created_at DESC",
                    (category,),
                )
            else:
                cursor.execute(
                    "SELECT * FROM learnings WHERE category = ? AND archived = 0 ORDER BY created_at DESC",
                    (category,),
                )
        else:
            cursor.execute(f"SELECT * FROM learnings{archive_filter} ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    # --- Episodes CRUD ---

    def add_episode(
        self,
        business_id: int,
        task_type: str,
        task_id: int,
        summary: str,
        outcome: str,
        outcome_details: str | None = None,
        key_decisions: list[str] | None = None,
        duration_seconds: int | None = None,
        tags: list[str] | None = None,
    ) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """INSERT INTO episodes
               (business_id, task_type, task_id, summary, outcome, outcome_details,
                key_decisions, duration_seconds, created_at, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                business_id,
                task_type,
                task_id,
                summary,
                outcome,
                outcome_details,
                json.dumps(key_decisions) if key_decisions else None,
                duration_seconds,
                self._now(),
                json.dumps(tags) if tags else None,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_episodes(
        self,
        business_id: int | None = None,
        task_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM episodes WHERE 1=1"
        params: list[Any] = []
        if business_id is not None:
            query += " AND business_id = ?"
            params.append(business_id)
        if task_type is not None:
            query += " AND task_type = ?"
            params.append(task_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor = self._conn.cursor()
        cursor.execute(query, params)
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            d = self._parse_episode_json(d)
            rows.append(d)
        return rows

    def get_episode(self, episode_id: int) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._parse_episode_json(dict(row))

    def _parse_episode_json(self, d: dict) -> dict:
        """Safely parse JSON fields in episode rows."""
        for field in ("key_decisions", "tags"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
        return d

    # --- Episode TTL ---

    def archive_old_episodes(self, max_age_days: int = 365) -> int:
        """Delete episodes older than *max_age_days*.

        Returns the number of deleted rows.
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        cursor = self._conn.execute(
            "DELETE FROM episodes WHERE created_at < ?", (cutoff,)
        )
        self._conn.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info("Archived %d episodes older than %d days", deleted, max_age_days)
        return deleted

    # --- Lifecycle ---

    def archive(self, table: str, item_id: int, vectors=None) -> None:
        """Mark an item as archived. Optionally delete from vector store."""
        if table not in ("facts", "decisions", "learnings"):
            raise ValueError(f"Invalid table: {table}")
        self._conn.execute(f"UPDATE {table} SET archived = 1 WHERE id = ?", (item_id,))
        self._conn.commit()
        if vectors is not None:
            try:
                vectors.delete_vectors(table, [str(item_id)])
            except Exception as e:
                logger.warning("Vector delete failed for %s/%d: %s", table, item_id, e)

    def unarchive(self, table: str, item_id: int) -> None:
        """Restore an archived item."""
        if table not in ("facts", "decisions", "learnings"):
            raise ValueError(f"Invalid table: {table}")
        self._conn.execute(f"UPDATE {table} SET archived = 0 WHERE id = ?", (item_id,))
        self._conn.commit()

    def list_archived(self, table: str, business_id: int | None = None) -> list[dict[str, Any]]:
        """List all archived items in a table."""
        if table not in ("facts", "decisions", "learnings"):
            raise ValueError(f"Invalid table: {table}")
        cursor = self._conn.cursor()
        if business_id is not None:
            bid_col = "business_id" if table != "learnings" else "source_business_id"
            cursor.execute(
                f"SELECT * FROM {table} WHERE archived = 1 AND {bid_col} = ? ORDER BY id",
                (business_id,),
            )
        else:
            cursor.execute(f"SELECT * FROM {table} WHERE archived = 1 ORDER BY id")
        return [dict(row) for row in cursor.fetchall()]

    def touch_accessed(self, table: str, item_ids: list[int]) -> None:
        """Bulk update last_accessed and increment access_count."""
        if not item_ids:
            return
        if table not in ("facts", "decisions", "learnings"):
            raise ValueError(f"Invalid table: {table}")
        now = self._now()
        placeholders = ",".join("?" for _ in item_ids)
        self._conn.execute(
            f"UPDATE {table} SET last_accessed = ?, access_count = access_count + 1 WHERE id IN ({placeholders})",
            [now] + item_ids,
        )
        self._conn.commit()

    def decay_stale(
        self,
        decay_factor: float = 0.95,
        stale_days: int = 7,
        archive_threshold: float = 0.1,
    ) -> dict:
        """Decay relevance scores for stale items and archive low-score ones.

        Returns {"decayed": N, "archived": N}.
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=stale_days)).isoformat()
        total_decayed = 0
        total_archived = 0

        for table in ("facts", "decisions", "learnings"):
            cursor = self._conn.execute(
                f"UPDATE {table} SET relevance_score = relevance_score * ? "
                f"WHERE (last_accessed IS NULL OR last_accessed < ?) AND archived = 0",
                (decay_factor, cutoff),
            )
            total_decayed += cursor.rowcount

            cursor = self._conn.execute(
                f"UPDATE {table} SET archived = 1 "
                f"WHERE relevance_score < ? AND archived = 0",
                (archive_threshold,),
            )
            total_archived += cursor.rowcount

        self._conn.commit()
        return {"decayed": total_decayed, "archived": total_archived}

    # --- Stats ---

    def stats(self) -> dict[str, int]:
        cursor = self._conn.cursor()
        counts = {}
        for table in ("businesses", "facts", "decisions", "relationships", "state", "learnings", "episodes"):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
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
