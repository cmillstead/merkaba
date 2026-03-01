# src/merkaba/security/audit.py
"""Dependency CVE auditing via pip-audit."""

import json
import subprocess
from dataclasses import dataclass


@dataclass
class CVEIssue:
    """A CVE found in a dependency."""
    package: str
    version: str
    cve_id: str
    description: str
    fix_version: str | None
    severity: str = "UNKNOWN"


def _run_pip_audit() -> str:
    """Run pip-audit and return JSON output."""
    try:
        result = subprocess.run(
            ["pip-audit", "--format=json", "--progress-spinner=off"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "[]"


def scan_dependencies() -> list[CVEIssue]:
    """Scan installed packages for known CVEs."""
    output = _run_pip_audit()

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []

    # pip-audit JSON format varies by version:
    # v2.6+: {"dependencies": [...], "fixes": [...]}
    # older: [{"name": ..., "vulns": [...]}, ...]
    if isinstance(data, dict):
        data = data.get("dependencies", [])

    issues = []
    for pkg in data:
        if not isinstance(pkg, dict):
            continue
        for vuln in pkg.get("vulns", []):
            fix_versions = vuln.get("fix_versions", [])
            issues.append(CVEIssue(
                package=pkg["name"],
                version=pkg["version"],
                cve_id=vuln["id"],
                description=vuln.get("description", ""),
                fix_version=fix_versions[0] if fix_versions else None,
            ))

    return issues
