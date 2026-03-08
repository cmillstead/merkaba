# src/merkaba/plugins/importer_openclaw.py
"""OpenClaw workspace migrator.

Maps OpenClaw workspace files to Merkaba business directories:
- SOUL.md     -> businesses/{id}/SOUL.md       (direct copy)
- USER.md     -> businesses/{id}/USER.md       (direct copy)
- HEARTBEAT.md -> businesses/{id}/HEARTBEAT.md (direct copy)
- AGENTS.md   -> businesses/{id}/.imported/    (stash only)
- TOOLS.md    -> businesses/{id}/.imported/    (stash only)
- IDENTITY.md -> businesses/{id}/.imported/    (stash only)

All originals are stashed in .imported/ for lossless round-trip reference.
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Files to copy directly to business dir
_DIRECT_COPY = {"SOUL.md", "USER.md", "HEARTBEAT.md"}
# Files to stash (not directly usable but preserved for reference)
_STASH_ONLY = {"AGENTS.md", "TOOLS.md", "IDENTITY.md"}


@dataclass
class MigrationResult:
    """Result of an OpenClaw workspace migration."""

    migrated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class OpenClawMigrator:
    """Migrates OpenClaw workspaces to Merkaba business directories."""

    def __init__(self, merkaba_home: Path | None = None):
        from merkaba.paths import merkaba_home as _merkaba_home
        self.merkaba_home = (
            Path(merkaba_home) if merkaba_home else Path(_merkaba_home())
        )

    def detect(self, workspace_path: Path) -> bool:
        """Detect if a directory is an OpenClaw workspace.

        Returns True if the directory contains a .openclaw/ directory
        or a SOUL.md file (the minimum OpenClaw workspace marker).
        """
        return (workspace_path / ".openclaw").is_dir() or (
            workspace_path / "SOUL.md"
        ).is_file()

    def migrate(self, workspace_path: Path, business_name: str) -> MigrationResult:
        """Migrate an OpenClaw workspace to a Merkaba business directory.

        Args:
            workspace_path: Path to the OpenClaw workspace.
            business_name: Name for the Merkaba business directory.

        Returns:
            MigrationResult with lists of migrated, skipped, and errored files.
        """
        result = MigrationResult()
        biz_dir = self.merkaba_home / "businesses" / business_name
        imported_dir = biz_dir / ".imported"
        biz_dir.mkdir(parents=True, exist_ok=True)
        imported_dir.mkdir(parents=True, exist_ok=True)

        for src_file in sorted(workspace_path.iterdir()):
            if not src_file.is_file():
                continue

            name = src_file.name

            try:
                # Always stash original in .imported/
                shutil.copy2(src_file, imported_dir / name)

                if name in _DIRECT_COPY:
                    shutil.copy2(src_file, biz_dir / name)
                    result.migrated.append(name)
                    logger.info("Copied %s to %s", name, biz_dir / name)
                elif name in _STASH_ONLY:
                    result.migrated.append(f"{name} (stashed)")
                    logger.info("Stashed %s in %s", name, imported_dir / name)
                else:
                    result.skipped.append(name)
                    logger.debug("Skipped unknown file %s", name)
            except OSError as exc:
                result.errors.append(f"{name}: {exc}")
                logger.error("Failed to migrate %s: %s", name, exc)

        return result
