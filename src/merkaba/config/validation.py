# src/merkaba/config/validation.py
"""Startup configuration validation with severity levels.

Surfaces issues at startup so users know when they're running in a degraded
mode and what to do about it.

ERROR: blocks functionality (no LLM available, corrupt DB)
WARNING: continues with degraded mode (no ChromaDB, incomplete routing)
INFO: configuration notes, version info
"""

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

logger = logging.getLogger("merkaba.config")


class Severity(IntEnum):
    """Issue severity — higher values are more severe."""

    INFO = 0
    WARNING = 1
    ERROR = 2


@dataclass
class ConfigIssue:
    """A single configuration issue found during validation."""

    severity: Severity
    component: str
    message: str
    hint: str | None = None


def validate_config(
    config: dict,
    base_dir: Path,
    *,
    _skip_runtime_checks: bool = False,
) -> list[ConfigIssue]:
    """Validate a configuration dict and return a list of issues.

    Args:
        config: The parsed config.json dict.
        base_dir: Merkaba home directory (~/.merkaba/).
        _skip_runtime_checks: Skip Ollama/ChromaDB connectivity checks
            (for unit testing).

    Returns:
        List of ConfigIssue objects, sorted by severity (errors first).
    """
    issues: list[ConfigIssue] = []

    _check_model_routing(config, issues)
    _check_auto_approve(config, issues)
    _check_business_prompts(base_dir, issues)

    if not _skip_runtime_checks:
        _check_ollama(issues)
        _check_chromadb(issues)

    # Sort by severity descending (ERROR first, then WARNING, then INFO)
    issues.sort(key=lambda i: i.severity, reverse=True)
    return issues


def _check_model_routing(config: dict, issues: list[ConfigIssue]) -> None:
    """Check that model routing has both simple and complex models set."""
    models = config.get("models", {})
    missing = []
    if not models.get("simple"):
        missing.append("simple")
    if not models.get("complex"):
        missing.append("complex")

    if missing:
        issues.append(ConfigIssue(
            severity=Severity.WARNING,
            component="model_routing",
            message=f"Model routing incomplete: missing {', '.join(missing)} model(s)",
            hint="Set models.simple and models.complex in config.json",
        ))


def _check_auto_approve(config: dict, issues: list[ConfigIssue]) -> None:
    """Warn if auto_approve_level is set to DESTRUCTIVE."""
    level = config.get("auto_approve_level", "")
    if isinstance(level, str) and level.upper() == "DESTRUCTIVE":
        issues.append(ConfigIssue(
            severity=Severity.WARNING,
            component="security",
            message=(
                "auto_approve_level is DESTRUCTIVE — the agent can delete, "
                "publish, and spend money without approval"
            ),
            hint="Consider lowering to SENSITIVE or MODERATE",
        ))


def _check_business_prompts(base_dir: Path, issues: list[ConfigIssue]) -> None:
    """Check that each business directory has a SOUL.md file."""
    biz_root = base_dir / "businesses"
    if not biz_root.is_dir():
        return

    for biz_dir in sorted(biz_root.iterdir()):
        if not biz_dir.is_dir():
            continue
        soul_path = biz_dir / "SOUL.md"
        if not soul_path.is_file():
            issues.append(ConfigIssue(
                severity=Severity.WARNING,
                component="prompts",
                message=f"Business '{biz_dir.name}' has no SOUL.md — using global fallback",
                hint=f"Create {soul_path} to customize the agent personality for this business",
            ))


def _check_ollama(issues: list[ConfigIssue]) -> None:
    """Check if Ollama is reachable."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2):
            pass
    except Exception:
        issues.append(ConfigIssue(
            severity=Severity.ERROR,
            component="llm",
            message="Ollama is not reachable at localhost:11434",
            hint="Start Ollama with: ollama serve",
        ))


def _check_chromadb(issues: list[ConfigIssue]) -> None:
    """Check if ChromaDB is importable for vector search."""
    try:
        import chromadb  # noqa: F401
    except ImportError:
        issues.append(ConfigIssue(
            severity=Severity.WARNING,
            component="memory",
            message="ChromaDB not installed — vector search disabled, keyword-only fallback",
            hint="Install with: pip install chromadb",
        ))


def print_startup_report(issues: list[ConfigIssue]) -> None:
    """Print a formatted startup report grouped by severity.

    Clean configs (no issues) produce no output.
    """
    if not issues:
        return

    # Group by severity
    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos = [i for i in issues if i.severity == Severity.INFO]

    print()

    if errors:
        print("=" * 60)
        print("  STARTUP ERRORS — functionality may be blocked")
        print("=" * 60)
        for issue in errors:
            print(f"  ERROR [{issue.component}] {issue.message}")
            if issue.hint:
                print(f"    -> {issue.hint}")
        print()

    if warnings:
        print("-" * 60)
        print("  STARTUP WARNINGS — running in degraded mode")
        print("-" * 60)
        for issue in warnings:
            print(f"  WARNING [{issue.component}] {issue.message}")
            if issue.hint:
                print(f"    -> {issue.hint}")
        print()

    if infos:
        for issue in infos:
            print(f"  INFO [{issue.component}] {issue.message}")
            if issue.hint:
                print(f"    -> {issue.hint}")
        print()
