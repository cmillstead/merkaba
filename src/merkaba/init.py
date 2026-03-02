# src/merkaba/init.py
"""Merkaba onboarding wizard — ``merkaba init``."""

import json
import shutil
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


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
