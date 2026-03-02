# src/merkaba/init.py
"""Merkaba onboarding wizard — ``merkaba init``."""

import json
import os
import shutil
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from merkaba.config.prompts import DEFAULT_SOUL, DEFAULT_USER

MERKABA_DIR = Path(os.path.expanduser("~/.merkaba"))

DEFAULT_CONFIG = {
    "models": {
        "simple": "qwen3:8b",
        "complex": "qwen3.5:122b",
    },
    "rate_limiting": {
        "max_concurrent": 2,
        "queue_depth_warning": 5,
    },
}

REQUIRED_MODELS = {
    "simple": "qwen3:8b",
    "complex": "qwen3.5:122b",
    "classifier": "qwen3:4b",
}

MODEL_DESCRIPTIONS = {
    "simple": "Fast responses, routing, classification",
    "complex": "Deep reasoning, tool use, long tasks",
    "classifier": "Safety checks, complexity routing",
}


@dataclass
class ModelStatus:
    """Result of Ollama availability and model check."""

    available: bool
    installed_models: list[str] = field(default_factory=list)
    missing_models: list[str] = field(default_factory=list)


def check_ollama() -> ModelStatus:
    """Check Ollama availability and installed models."""
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
    except Exception:
        return ModelStatus(
            available=False,
            missing_models=list(REQUIRED_MODELS.values()),
        )

    installed = [m["name"] for m in data.get("models", [])]
    installed_set = set(installed)
    missing = [m for m in REQUIRED_MODELS.values() if m not in installed_set]

    return ModelStatus(
        available=True,
        installed_models=installed,
        missing_models=missing,
    )


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


def run_preflight(*, force: bool = False) -> ModelStatus:
    """Phase 1: Check prerequisites, create dirs, seed defaults.

    Returns ModelStatus so the caller knows if the interview can run.
    """
    print("\n  Setting up Merkaba...\n")

    # 1. Create directories
    for subdir in ("logs", "conversations", "plugins"):
        (MERKABA_DIR / subdir).mkdir(parents=True, exist_ok=True)

    # 2. Seed config.json
    config_path = MERKABA_DIR / "config.json"
    action = check_file_safety(config_path, json.dumps(DEFAULT_CONFIG, indent=2), force=force)
    if action != FileAction.SKIP:
        config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        print(f"  Created {config_path}")

    # 3. Seed SOUL.md
    soul_path = MERKABA_DIR / "SOUL.md"
    action = check_file_safety(soul_path, DEFAULT_SOUL, force=force)
    if action != FileAction.SKIP:
        soul_path.write_text(DEFAULT_SOUL, encoding="utf-8")
        print(f"  Created {soul_path}")

    # 4. Seed USER.md
    user_path = MERKABA_DIR / "USER.md"
    action = check_file_safety(user_path, DEFAULT_USER, force=force)
    if action != FileAction.SKIP:
        user_path.write_text(DEFAULT_USER, encoding="utf-8")
        print(f"  Created {user_path}")

    # 5. Check Ollama and models
    status = check_ollama()
    if not status.available:
        print("\n  Ollama is not running.")
        print("  Start it with: ollama serve\n")
    else:
        print("\n  Ollama is running.")
        _print_model_inventory(status)

    return status


def _print_model_inventory(status: ModelStatus) -> None:
    """Print model availability table."""
    print("\n  Merkaba uses three models:\n")
    for role, model in REQUIRED_MODELS.items():
        desc = MODEL_DESCRIPTIONS[role]
        installed = model in status.installed_models
        marker = "+" if installed else "-"
        print(f"    {marker} {role.capitalize():12s} ({model:20s})  {desc}")

    if status.missing_models:
        print("\n  To install missing models:")
        for model in status.missing_models:
            print(f"    ollama pull {model}")
    print()
