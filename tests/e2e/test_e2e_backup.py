# tests/e2e/test_e2e_backup.py
"""End-to-end tests for the backup/restore cycle.

Uses BackupManager directly (not the CLI) so we can point merkaba_dir
at a temporary directory and avoid touching ~/.merkaba/.
"""

import sqlite3
import time

import pytest

from merkaba.memory.store import MemoryStore
from merkaba.orchestration.backup import BackupManager

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_db(path):
    """Create a minimal SQLite DB with a single test row."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'original')")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 1. run_backup creates a backup directory with files
# ---------------------------------------------------------------------------

def test_backup_run_creates_backup(tmp_path):
    """Create DBs, run backup, verify backup directory exists with files."""
    merkaba_dir = tmp_path / "merkaba"
    merkaba_dir.mkdir()

    # Create the DBs that BackupManager looks for
    for db_name in ("memory.db", "tasks.db", "actions.db"):
        _create_db(merkaba_dir / db_name)

    mgr = BackupManager(merkaba_dir=merkaba_dir)
    backup_path = mgr.run_backup()

    assert backup_path.exists()
    assert backup_path.is_dir()

    backed_up_files = [f.name for f in backup_path.iterdir() if f.is_file()]
    assert "memory.db" in backed_up_files
    assert "tasks.db" in backed_up_files
    assert "actions.db" in backed_up_files


# ---------------------------------------------------------------------------
# 2. list_backups returns empty when no backups exist
# ---------------------------------------------------------------------------

def test_backup_list_empty(tmp_path):
    """No backups yet — list returns an empty list."""
    merkaba_dir = tmp_path / "merkaba"
    merkaba_dir.mkdir()

    mgr = BackupManager(merkaba_dir=merkaba_dir)
    assert mgr.list_backups() == []


# ---------------------------------------------------------------------------
# 3. list_backups returns entries after a run
# ---------------------------------------------------------------------------

def test_backup_list_after_run(tmp_path):
    """Create a DB, run backup, list returns 1 entry with a timestamp key."""
    merkaba_dir = tmp_path / "merkaba"
    merkaba_dir.mkdir()
    _create_db(merkaba_dir / "memory.db")

    mgr = BackupManager(merkaba_dir=merkaba_dir)
    mgr.run_backup()

    backups = mgr.list_backups()
    assert len(backups) == 1

    entry = backups[0]
    assert "timestamp" in entry
    assert "path" in entry
    assert "files" in entry
    # Timestamp should look like YYYYMMDD_HHMMSS
    assert len(entry["timestamp"]) == 15
    assert "_" in entry["timestamp"]


# ---------------------------------------------------------------------------
# 4. restore recovers original data after modification
# ---------------------------------------------------------------------------

def test_backup_restore_recovers_data(tmp_path):
    """Backup memory.db, modify it, restore — original data is back."""
    merkaba_dir = tmp_path / "merkaba"
    merkaba_dir.mkdir()

    # Create a real memory.db via MemoryStore
    db_path = str(merkaba_dir / "memory.db")
    store = MemoryStore(db_path=db_path)
    biz_id = store.add_business("Original Biz", "ecommerce")
    store.close()

    # Backup
    mgr = BackupManager(merkaba_dir=merkaba_dir)
    mgr.run_backup()

    # Modify — add a second business
    store = MemoryStore(db_path=db_path)
    store.add_business("New Biz", "saas")
    businesses_before_restore = store.list_businesses()
    assert len(businesses_before_restore) == 2
    store.close()

    # Restore from backup
    backups = mgr.list_backups()
    mgr.restore(backups[0]["timestamp"], "memory.db")

    # Verify the DB matches the backup state (only "Original Biz")
    store = MemoryStore(db_path=db_path)
    businesses = store.list_businesses()
    assert len(businesses) == 1
    assert businesses[0]["name"] == "Original Biz"
    store.close()


# ---------------------------------------------------------------------------
# 5. restore with non-existent timestamp raises FileNotFoundError
# ---------------------------------------------------------------------------

def test_backup_restore_nonexistent(tmp_path):
    """Restore with a bad timestamp raises FileNotFoundError."""
    merkaba_dir = tmp_path / "merkaba"
    merkaba_dir.mkdir()

    mgr = BackupManager(merkaba_dir=merkaba_dir)

    with pytest.raises(FileNotFoundError):
        mgr.restore("99990101_000000", "memory.db")


# ---------------------------------------------------------------------------
# 6. prune keeps only max_backups
# ---------------------------------------------------------------------------

def test_backup_prune_keeps_max(tmp_path):
    """Create 10 backups, prune with max_backups=3, verify only 3 remain."""
    merkaba_dir = tmp_path / "merkaba"
    merkaba_dir.mkdir()
    _create_db(merkaba_dir / "memory.db")

    mgr = BackupManager(merkaba_dir=merkaba_dir, max_backups=3)

    for _ in range(10):
        mgr.run_backup()
        # Ensure each backup gets a unique timestamp directory name
        time.sleep(1.1)

    backups = mgr.list_backups()
    assert len(backups) == 3

    # The remaining backups should be the 3 most recent (sorted ascending)
    timestamps = [b["timestamp"] for b in backups]
    assert timestamps == sorted(timestamps)
