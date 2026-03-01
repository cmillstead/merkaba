# tests/test_backup.py
import json
import sqlite3
from pathlib import Path

import pytest

from merkaba.orchestration.backup import BackupManager


def _make_db(path: Path, table: str = "test", rows: list[tuple] = None):
    """Create a real SQLite DB with optional data."""
    conn = sqlite3.connect(str(path))
    conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, value TEXT)")
    for row in rows or []:
        conn.execute(f"INSERT INTO {table} (id, value) VALUES (?, ?)", row)
    conn.commit()
    conn.close()


def test_run_backup_creates_timestamped_dir(tmp_path):
    _make_db(tmp_path / "memory.db")
    _make_db(tmp_path / "tasks.db")

    mgr = BackupManager(merkaba_dir=tmp_path)
    result = mgr.run_backup()

    assert result.exists()
    assert result.parent == tmp_path / "backups"
    # Timestamp format: YYYYMMDD_HHMMSS
    assert len(result.name) == 15
    assert (result / "memory.db").exists()
    assert (result / "tasks.db").exists()


def test_backup_uses_sqlite_online_api(tmp_path):
    _make_db(tmp_path / "memory.db", rows=[(1, "hello"), (2, "world")])

    mgr = BackupManager(merkaba_dir=tmp_path)
    result = mgr.run_backup()

    # Open the backup and verify data was transferred
    conn = sqlite3.connect(str(result / "memory.db"))
    rows = conn.execute("SELECT id, value FROM test ORDER BY id").fetchall()
    conn.close()
    assert rows == [(1, "hello"), (2, "world")]


def test_backup_skips_missing_dbs(tmp_path):
    # Only create one DB, not all four
    _make_db(tmp_path / "memory.db")

    mgr = BackupManager(merkaba_dir=tmp_path)
    result = mgr.run_backup()

    assert (result / "memory.db").exists()
    assert not (result / "tasks.db").exists()
    assert not (result / "actions.db").exists()
    assert not (result / "research.db").exists()


def test_backup_copies_config_json(tmp_path):
    _make_db(tmp_path / "memory.db")
    config = {"api_key": "test123"}
    (tmp_path / "config.json").write_text(json.dumps(config))

    mgr = BackupManager(merkaba_dir=tmp_path)
    result = mgr.run_backup()

    backed_up = json.loads((result / "config.json").read_text())
    assert backed_up == config


def test_backup_copies_conversations(tmp_path):
    _make_db(tmp_path / "memory.db")
    convos = tmp_path / "conversations"
    convos.mkdir()
    (convos / "chat1.json").write_text('{"messages": []}')
    (convos / "chat2.json").write_text('{"messages": []}')

    mgr = BackupManager(merkaba_dir=tmp_path)
    result = mgr.run_backup()

    backed_convos = result / "conversations"
    assert backed_convos.is_dir()
    assert (backed_convos / "chat1.json").exists()
    assert (backed_convos / "chat2.json").exists()


def test_prune_keeps_max_backups(tmp_path):
    mgr = BackupManager(merkaba_dir=tmp_path, max_backups=7)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create 10 fake backup dirs
    for i in range(10):
        d = backup_dir / f"20260228_{i:06d}"
        d.mkdir()
        (d / "memory.db").write_text("fake")

    mgr.prune_old_backups()

    remaining = sorted(d.name for d in backup_dir.iterdir() if d.is_dir())
    assert len(remaining) == 7
    # Oldest 3 should be pruned
    assert remaining[0] == "20260228_000003"


def test_list_backups_returns_metadata(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    for ts in ["20260101_120000", "20260102_120000", "20260103_120000"]:
        d = backup_dir / ts
        d.mkdir()
        (d / "memory.db").write_text("fake")
        (d / "tasks.db").write_text("fake")

    mgr = BackupManager(merkaba_dir=tmp_path)
    backups = mgr.list_backups()

    assert len(backups) == 3
    assert backups[0]["timestamp"] == "20260101_120000"
    assert "memory.db" in backups[0]["files"]
    assert "tasks.db" in backups[0]["files"]


def test_restore_copies_backup_to_source(tmp_path):
    _make_db(tmp_path / "memory.db", rows=[(1, "original")])

    mgr = BackupManager(merkaba_dir=tmp_path)
    backup_path = mgr.run_backup()

    # Modify the source DB
    conn = sqlite3.connect(str(tmp_path / "memory.db"))
    conn.execute("UPDATE test SET value = 'modified' WHERE id = 1")
    conn.commit()
    conn.close()

    # Restore from backup
    mgr.restore(backup_path.name, "memory.db")

    # Verify restored data matches original
    conn = sqlite3.connect(str(tmp_path / "memory.db"))
    rows = conn.execute("SELECT value FROM test WHERE id = 1").fetchone()
    conn.close()
    assert rows[0] == "original"


def test_restore_creates_pre_restore_safety_copy(tmp_path):
    _make_db(tmp_path / "memory.db", rows=[(1, "current")])

    mgr = BackupManager(merkaba_dir=tmp_path)
    backup_path = mgr.run_backup()

    mgr.restore(backup_path.name, "memory.db")

    safety = tmp_path / "memory.db.pre-restore"
    assert safety.exists()
    # Safety copy should have the pre-restore data
    conn = sqlite3.connect(str(safety))
    rows = conn.execute("SELECT value FROM test WHERE id = 1").fetchone()
    conn.close()
    assert rows[0] == "current"


def test_restore_missing_backup_raises(tmp_path):
    mgr = BackupManager(merkaba_dir=tmp_path)

    with pytest.raises(FileNotFoundError):
        mgr.restore("nonexistent_timestamp", "memory.db")
