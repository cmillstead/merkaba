# src/merkaba/init.py
"""Onboarding / first-run setup for Merkaba.

Creates the ~/.merkaba/ directory structure, config.json with sensible
defaults, copies SOUL.md and USER.md from .example templates, and
initializes the SQLite databases (memory, tasks, actions).
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories created inside MERKABA_HOME
_SUBDIRS = ("conversations", "plugins", "businesses", "backups", "logs")

from merkaba.config.defaults import DEFAULT_MODELS

# Default config.json contents
DEFAULT_CONFIG: dict = {
    "models": {
        "complex": DEFAULT_MODELS["complex"],
        "simple": DEFAULT_MODELS["simple"],
        "classifier": DEFAULT_MODELS["classifier"],
    },
    "auto_approve_level": "MODERATE",
}

# Where the .example templates live inside the merkaba package
_TEMPLATES_DIR = Path(__file__).resolve().parent / "config"


@dataclass
class InitResult:
    """Summary of what the init process created or skipped."""

    home_dir: Path
    created_dirs: list[str] = field(default_factory=list)
    config_written: bool = False
    soul_copied: bool = False
    user_copied: bool = False
    databases_initialized: list[str] = field(default_factory=list)
    ollama_available: bool = False
    already_initialized: bool = False


def run_init(
    merkaba_home: Path | None = None,
    *,
    force: bool = False,
    skip_ollama_check: bool = False,
) -> InitResult:
    """Run the full onboarding sequence.

    Args:
        merkaba_home: Override for ~/.merkaba/ (used in tests).
        force: Re-create config even if it already exists.
        skip_ollama_check: Skip the Ollama connectivity check.

    Returns:
        InitResult summarizing what was created.
    """
    if merkaba_home is None:
        from merkaba.paths import merkaba_home as _merkaba_home
        merkaba_home = Path(_merkaba_home())

    result = InitResult(home_dir=merkaba_home)

    # Detect if already initialized (config.json exists)
    config_path = merkaba_home / "config.json"
    if config_path.is_file() and not force:
        result.already_initialized = True

    # 1. Create home directory and subdirectories
    _create_directories(merkaba_home, result)

    # 2. Write config.json
    _write_config(merkaba_home, result, force=force)

    # 3. Copy .example templates
    _copy_templates(merkaba_home, result, force=force)

    # 4. Initialize databases
    _init_databases(merkaba_home, result)

    # 5. Check Ollama
    if not skip_ollama_check:
        result.ollama_available = _check_ollama()

    return result


def _create_directories(home: Path, result: InitResult) -> None:
    """Ensure ~/.merkaba/ and its subdirectories exist."""
    if not home.exists():
        home.mkdir(parents=True, exist_ok=True)
        result.created_dirs.append(str(home))

    for subdir in _SUBDIRS:
        path = home / subdir
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            result.created_dirs.append(subdir)


def _write_config(home: Path, result: InitResult, *, force: bool = False) -> None:
    """Write config.json with defaults if it does not exist (or force)."""
    config_path = home / "config.json"
    if config_path.is_file() and not force:
        return

    config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    result.config_written = True


def _copy_templates(home: Path, result: InitResult, *, force: bool = False) -> None:
    """Copy SOUL.md.example and USER.md.example into home if missing."""
    for name, attr in [("SOUL.md", "soul_copied"), ("USER.md", "user_copied")]:
        dest = home / name
        src = _TEMPLATES_DIR / f"{name}.example"

        if dest.is_file() and not force:
            continue
        if not src.is_file():
            logger.warning("Template %s not found at %s", name, src)
            continue

        shutil.copy2(str(src), str(dest))
        setattr(result, attr, True)


def _init_databases(home: Path, result: InitResult) -> None:
    """Touch the SQLite databases so their schemas are created."""
    # Import lazily to avoid circular imports and heavy deps at module level
    from merkaba.memory.store import MemoryStore
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.approval.queue import ActionQueue

    db_specs = [
        ("memory.db", MemoryStore),
        ("tasks.db", TaskQueue),
        ("actions.db", ActionQueue),
    ]

    for db_name, cls in db_specs:
        db_path = str(home / db_name)
        if not (home / db_name).is_file():
            store = cls(db_path=db_path)
            store.close()
            result.databases_initialized.append(db_name)
        else:
            # Database already exists, but ensure schema is up to date
            store = cls(db_path=db_path)
            store.close()


def _check_ollama() -> bool:
    """Return True if Ollama is reachable at localhost:11434."""
    try:
        import urllib.request

        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2):
            pass
        return True
    except Exception:
        return False
