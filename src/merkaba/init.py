# src/merkaba/init.py
"""Merkaba onboarding wizard — ``merkaba init``."""

import shutil
from enum import Enum
from pathlib import Path


class FileAction(Enum):
    """Result of a file safety check."""

    WRITE = "write"
    SKIP = "skip"
    BACKUP = "backup"


def check_file_safety(
    path: Path,
    default_content: str,
    *,
    force: bool = False,
) -> FileAction:
    """Check if a file can be safely written.

    Returns:
        WRITE if the file is missing or matches the default.
        SKIP if user chose to skip.
        BACKUP if user chose to backup (or --force was used).
    """
    if not path.exists():
        return FileAction.WRITE

    existing = path.read_text(encoding="utf-8")
    if existing.strip() == default_content.strip():
        return FileAction.WRITE

    # File has been user-edited
    if force:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        return FileAction.BACKUP

    print(f"\n  {path.name} has been customized.")
    choice = input("  [o]verwrite / [s]kip / [b]ackup and overwrite? ").strip().lower()

    if choice == "b":
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        return FileAction.BACKUP
    elif choice == "o":
        return FileAction.WRITE
    else:
        return FileAction.SKIP
