# src/merkaba/db.py
"""Shared SQLite connection factory with standard Merkaba settings."""

import os
import sqlite3
from pathlib import Path


def create_connection(
    db_path: str | Path,
    *,
    check_same_thread: bool = False,
    foreign_keys: bool = True,
) -> sqlite3.Connection:
    """Create a SQLite connection with standard Merkaba settings.

    Handles the common boilerplate: directory creation, secure permissions,
    WAL journal mode, row factory, and optional foreign key enforcement.
    """
    from merkaba.security.file_permissions import ensure_secure_permissions

    path = Path(db_path)
    db_dir = str(path.parent)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        ensure_secure_permissions(db_dir)
    conn = sqlite3.connect(str(path), check_same_thread=check_same_thread)
    ensure_secure_permissions(str(path))
    conn.row_factory = sqlite3.Row
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn
