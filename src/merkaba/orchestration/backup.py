# src/merkaba/orchestration/backup.py
import json
import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from merkaba.config.utils import deep_strip_secrets
from merkaba.paths import merkaba_home as _merkaba_home

try:
    from merkaba.security.file_permissions import ensure_secure_permissions
except ImportError:  # pragma: no cover
    ensure_secure_permissions = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _encrypt_file(path: Path, key: bytes) -> Path:
    """Encrypt a file with Fernet, write <path>.enc, delete original.

    Returns the path to the encrypted file.
    """
    from cryptography.fernet import Fernet  # noqa: PLC0415

    f = Fernet(key)
    plaintext = path.read_bytes()
    ciphertext = f.encrypt(plaintext)
    enc_path = path.with_suffix(path.suffix + ".enc")
    enc_path.write_bytes(ciphertext)
    path.unlink()
    return enc_path


def _get_or_create_backup_key() -> bytes:
    """Return the backup encryption key from keyring, generating one if absent."""
    import keyring  # noqa: PLC0415
    from cryptography.fernet import Fernet  # noqa: PLC0415

    stored = keyring.get_password("merkaba", "backup_encryption_key")
    if stored:
        return stored.encode()
    key = Fernet.generate_key()
    keyring.set_password("merkaba", "backup_encryption_key", key.decode())
    logger.info("Generated new backup encryption key and stored in keychain")
    return key


DBS_TO_BACKUP = ["memory.db", "tasks.db", "actions.db", "research.db"]


@dataclass
class BackupManager:
    """Manages backup and restore of Merkaba's SQLite databases and config."""

    merkaba_dir: Path = field(
        default_factory=lambda: Path(_merkaba_home())
    )
    backup_dir: Path = field(default=None)
    max_backups: int = 7

    def __post_init__(self):
        if self.backup_dir is None:
            self.backup_dir = self.merkaba_dir / "backups"

    def run_backup(self, encrypt: bool = False) -> Path:
        """Create a timestamped backup of all databases and config.

        Args:
            encrypt: When True, each backup file is encrypted with Fernet using a
                key stored in (or generated and stored in) the system keychain under
                the service "merkaba" / account "backup_encryption_key".  The
                encrypted files are written with an additional ".enc" suffix and the
                plaintext copies are deleted.  Requires the ``cryptography`` and
                ``keyring`` packages; if either is missing a warning is logged and
                the backup proceeds without encryption.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / timestamp
        dest.mkdir(parents=True, exist_ok=True)

        # Secure permissions on the backup directory tree.
        if ensure_secure_permissions is not None:
            ensure_secure_permissions(str(self.backup_dir))
            ensure_secure_permissions(str(dest))

        # Resolve encryption key once (if requested).
        enc_key: bytes | None = None
        if encrypt:
            try:
                enc_key = _get_or_create_backup_key()
            except ImportError as exc:
                logger.warning(
                    "Backup encryption requested but a required package is missing "
                    "(%s). Proceeding without encryption.",
                    exc,
                )
                enc_key = None

        if enc_key is None:
            logger.warning(
                "Creating unencrypted backup. Sensitive data in databases "
                "will not be encrypted at rest."
            )

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
            if enc_key is not None:
                dst_path = _encrypt_file(dst_path, enc_key)
            logger.info("Backed up %s", dst_path.name)

        # Copy config.json if present, stripping sensitive keys
        config_src = self.merkaba_dir / "config.json"
        if config_src.exists():
            config_dst = dest / "config.json"
            try:
                raw_config = json.loads(config_src.read_text())
                stripped = deep_strip_secrets(raw_config)
                config_dst.write_text(json.dumps(stripped, indent=2))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Skipping config backup — could not strip secrets: %s",
                    exc,
                )
            if enc_key is not None:
                _encrypt_file(config_dst, enc_key)

        # Copy conversations directory if present
        convos_src = self.merkaba_dir / "conversations"
        if convos_src.is_dir():
            shutil.copytree(str(convos_src), str(dest / "conversations"))
            if enc_key is not None:
                # Encrypt each file inside the conversations directory
                for conv_file in (dest / "conversations").rglob("*"):
                    if conv_file.is_file():
                        _encrypt_file(conv_file, enc_key)

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
