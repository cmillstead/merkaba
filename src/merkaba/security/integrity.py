"""File integrity checking via SHA256 hashes."""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IntegrityReport:
    """Results of integrity check."""
    modified: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.modified or self.added or self.removed)


def compute_file_hash(file_path: Path) -> str | None:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file to hash

    Returns:
        Hex digest of SHA256 hash, or None if file doesn't exist
    """
    try:
        with open(file_path, "rb") as f:
            sha256 = hashlib.sha256()
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
            return sha256.hexdigest()
    except FileNotFoundError:
        return None


def compute_directory_hashes(directory: Path, pattern: str = "*") -> dict[str, str]:
    """Compute SHA256 hashes for all files in a directory.

    Args:
        directory: Path to the directory to hash
        pattern: Glob pattern to match files (default: "*")

    Returns:
        Dictionary mapping relative file paths to their SHA256 hashes
    """
    hashes = {}
    if not directory.exists():
        return hashes

    for file_path in directory.glob(pattern):
        if file_path.is_file():
            file_hash = compute_file_hash(file_path)
            if file_hash is not None:
                relative_path = str(file_path.relative_to(directory))
                hashes[relative_path] = file_hash

    return hashes


def compare_with_baseline(
    current: dict[str, str],
    baseline: dict[str, str]
) -> IntegrityReport:
    """Compare current hashes against baseline."""
    report = IntegrityReport()

    current_files = set(current.keys())
    baseline_files = set(baseline.keys())

    # Check for modified files
    for path in current_files & baseline_files:
        if current[path] != baseline[path]:
            report.modified.append(path)

    # Check for added files
    report.added = sorted(current_files - baseline_files)

    # Check for removed files
    report.removed = sorted(baseline_files - current_files)

    return report


def save_baseline(hashes: dict[str, str], path: Path) -> None:
    """Save hashes to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(hashes, f, indent=2, sort_keys=True)


def load_baseline(path: Path) -> dict[str, str]:
    """Load hashes from a JSON file."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
