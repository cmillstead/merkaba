# src/merkaba/orchestration/backup.py
import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DBS_TO_BACKUP = ["memory.db", "tasks.db", "actions.db", "research.db"]


@dataclass
class BackupManager:
    """Manages backup and restore of Merkaba's SQLite databases and config."""

    merkaba_dir: Path = field(
        default_factory=lambda: Path(os.path.expanduser("~/.merkaba"))
    )
    backup_dir: Path = field(default=None)
    max_backups: int = 7

    def __post_init__(self):
        if self.backup_dir is None:
            self.backup_dir = self.merkaba_dir / "backups"

    def run_backup(self) -> Path:
        """Create a timestamped backup of all databases and config."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / timestamp
        dest.mkdir(parents=True, exist_ok=True)

        # Backup SQLite databases using online backup API
        for db_name in DBS_TO_BACKUP:
            src_path = self.merkaba_dir / db_name
            if not src_path.exists():
                logger.debug("Skipping %s (not found)", db_name)
                continue
            dst_path = dest / db_name
            src_conn = None
            dst_conn = None
            try:
                src_conn = sqlite3.connect(str(src_path))
                dst_conn = sqlite3.connect(str(dst_path))
                src_conn.backup(dst_conn)
            finally:
                if dst_conn:
                    dst_conn.close()
                if src_conn:
                    src_conn.close()
            logger.info("Backed up %s", db_name)

        # Copy config.json if present
        config_src = self.merkaba_dir / "config.json"
        if config_src.exists():
            shutil.copy2(str(config_src), str(dest / "config.json"))

        # Copy conversations directory if present
        convos_src = self.merkaba_dir / "conversations"
        if convos_src.is_dir():
            shutil.copytree(str(convos_src), str(dest / "conversations"))

        self.prune_old_backups()
        logger.info("Backup complete: %s", dest)
        return dest

    def prune_old_backups(self):
        """Remove oldest backups beyond max_backups limit."""
        if not self.backup_dir.exists():
            return
        dirs = sorted(
            [d for d in self.backup_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )
        while len(dirs) > self.max_backups:
            oldest = dirs.pop(0)
            shutil.rmtree(str(oldest))
            logger.info("Pruned old backup: %s", oldest.name)

    def list_backups(self) -> list[dict]:
        """Return metadata for each backup directory."""
        if not self.backup_dir.exists():
            return []
        result = []
        dirs = sorted(
            [d for d in self.backup_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )
        for d in dirs:
            files = [f.name for f in d.iterdir() if f.is_file()]
            # Also count conversation files if present
            convos_dir = d / "conversations"
            if convos_dir.is_dir():
                files.append(f"conversations/ ({len(list(convos_dir.iterdir()))} files)")
            result.append({
                "timestamp": d.name,
                "path": str(d),
                "files": files,
            })
        return result

    def restore(self, timestamp: str, db_name: str):
        """Restore a specific database from a backup.

        Creates a .pre-restore safety copy of the current DB before overwriting.
        """
        backup_path = self.backup_dir / timestamp / db_name
        if not backup_path.exists():
            raise FileNotFoundError(
                f"Backup not found: {backup_path}"
            )

        current_path = self.merkaba_dir / db_name
        # Create safety copy before restore
        if current_path.exists():
            safety_path = self.merkaba_dir / f"{db_name}.pre-restore"
            shutil.copy2(str(current_path), str(safety_path))
            logger.info("Safety copy: %s", safety_path)

        shutil.copy2(str(backup_path), str(current_path))
        logger.info("Restored %s from %s", db_name, timestamp)
