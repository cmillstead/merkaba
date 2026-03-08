# tests/test_db.py
"""Tests for merkaba.db connection factory."""

import os

from merkaba.db import create_connection


def test_create_connection_wal_mode(tmp_path):
    """Verify that create_connection enables WAL journal mode."""
    db_file = tmp_path / "test.db"
    conn = create_connection(db_file)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
    finally:
        conn.close()


def test_create_connection_foreign_keys(tmp_path):
    """Verify that create_connection enables foreign key enforcement by default."""
    db_file = tmp_path / "test.db"
    conn = create_connection(db_file)
    try:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


def test_create_connection_foreign_keys_disabled(tmp_path):
    """Verify that foreign_keys=False skips PRAGMA foreign_keys."""
    db_file = tmp_path / "test.db"
    conn = create_connection(db_file, foreign_keys=False)
    try:
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 0
    finally:
        conn.close()


def test_create_connection_creates_parent_dirs(tmp_path):
    """Verify that create_connection creates parent directories."""
    db_file = tmp_path / "sub" / "dir" / "test.db"
    conn = create_connection(db_file)
    try:
        assert os.path.isdir(tmp_path / "sub" / "dir")
        assert os.path.isfile(db_file)
    finally:
        conn.close()


def test_create_connection_row_factory(tmp_path):
    """Verify that row_factory is set to sqlite3.Row."""
    import sqlite3

    db_file = tmp_path / "test.db"
    conn = create_connection(db_file)
    try:
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()
