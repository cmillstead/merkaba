# src/friday/security/scanner.py
"""Security scanner orchestration for Friday AI agent."""

from dataclasses import dataclass, field
from pathlib import Path

from friday.security.integrity import (
    compute_directory_hashes,
    compare_with_baseline,
    load_baseline,
    save_baseline,
)
from friday.security.audit import scan_dependencies, CVEIssue
from friday.plugins.skills import scan_skill_content


# Core security files that quick_scan checks
CORE_SECURITY_FILES = [
    "security/permissions.py",
    "security/validation.py",
    "security/secrets.py",
    "security/integrity.py",
    "security/audit.py",
    "security/scanner.py",
]


@dataclass
class SecurityReport:
    """Results of a security scan."""

    integrity_issues: list[str] = field(default_factory=list)
    cve_issues: list[CVEIssue] = field(default_factory=list)
    code_warnings: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Check if any issues were found."""
        return bool(self.integrity_issues or self.cve_issues or self.code_warnings)

    def summary(self) -> str:
        """Generate a human-readable summary of the scan results."""
        lines = ["Security Scan Summary", "=" * 40]

        if not self.has_issues:
            lines.append("No issues found.")
            return "\n".join(lines)

        if self.integrity_issues:
            lines.append(f"\nIntegrity Issues ({len(self.integrity_issues)}):")
            for issue in self.integrity_issues:
                lines.append(f"  - {issue}")

        if self.cve_issues:
            lines.append(f"\nCVE Issues ({len(self.cve_issues)}):")
            for cve in self.cve_issues:
                lines.append(f"  - {cve.package}@{cve.version}: {cve.cve_id}")
                if cve.fix_version:
                    lines.append(f"    Fix available: {cve.fix_version}")

        if self.code_warnings:
            lines.append(f"\nCode Warnings ({len(self.code_warnings)}):")
            for warning in self.code_warnings:
                lines.append(f"  - {warning}")

        return "\n".join(lines)


class SecurityScanner:
    """Orchestrates security scanning across multiple checks."""

    def __init__(
        self,
        source_dir: Path | None = None,
        user_baseline: Path | None = None,
        repo_baseline: Path | None = None,
    ):
        """Initialize the security scanner.

        Args:
            source_dir: Directory containing source code to scan.
            user_baseline: Path to user's baseline hash file.
            repo_baseline: Path to repository's baseline hash file.
        """
        self.source_dir = source_dir or Path.cwd()
        self.user_baseline = user_baseline
        self.repo_baseline = repo_baseline

    def quick_scan(self) -> SecurityReport:
        """Run a quick scan checking only core security files.

        This is faster than full_scan() and focuses on security-critical
        files that should rarely change.

        Returns:
            SecurityReport with any integrity issues found.
        """
        integrity_issues = self._check_integrity(quick=True)
        return SecurityReport(
            integrity_issues=integrity_issues,
            cve_issues=[],
            code_warnings=[],
        )

    def full_scan(self) -> SecurityReport:
        """Run a full security scan.

        Performs:
        - Full integrity check of all source files
        - Dependency CVE audit
        - Self-scan for dangerous patterns

        Returns:
            SecurityReport with all issues found.
        """
        integrity_issues = self._check_integrity(quick=False)
        cve_issues = self._scan_dependencies()
        code_warnings = self._self_scan()

        return SecurityReport(
            integrity_issues=integrity_issues,
            cve_issues=cve_issues,
            code_warnings=code_warnings,
        )

    def _check_integrity(self, quick: bool = False) -> list[str]:
        """Check file integrity against baseline.

        Args:
            quick: If True, only check core security files.

        Returns:
            List of integrity issue descriptions.
        """
        issues = []

        # Load baseline (prefer user baseline, fall back to repo baseline)
        baseline = {}
        if self.user_baseline and self.user_baseline.exists():
            baseline = load_baseline(self.user_baseline)
        elif self.repo_baseline and self.repo_baseline.exists():
            baseline = load_baseline(self.repo_baseline)

        if not baseline:
            return issues  # No baseline to compare against

        # Compute current hashes
        if quick:
            # Only check core security files
            current = {}
            for rel_path in CORE_SECURITY_FILES:
                file_path = self.source_dir / rel_path
                if file_path.exists():
                    from friday.security.integrity import compute_file_hash
                    file_hash = compute_file_hash(file_path)
                    if file_hash:
                        current[rel_path] = file_hash
        else:
            # Check all Python files
            current = compute_directory_hashes(self.source_dir, "**/*.py")

        # Compare with baseline
        report = compare_with_baseline(current, baseline)

        if report.modified:
            for path in report.modified:
                issues.append(f"{path} modified")

        if report.added:
            for path in report.added:
                issues.append(f"{path} added")

        if report.removed:
            for path in report.removed:
                issues.append(f"{path} removed")

        return issues

    def _scan_dependencies(self) -> list[CVEIssue]:
        """Scan dependencies for known CVEs.

        Returns:
            List of CVE issues found.
        """
        return scan_dependencies()

    def _self_scan(self) -> list[str]:
        """Scan source files for dangerous patterns.

        Returns:
            List of warning messages.
        """
        warnings = []

        if not self.source_dir.exists():
            return warnings

        # Scan all Python files in source directory
        for py_file in self.source_dir.glob("**/*.py"):
            if py_file.is_file():
                try:
                    content = py_file.read_text()
                    file_warnings = scan_skill_content(content)
                    for warning in file_warnings:
                        rel_path = py_file.relative_to(self.source_dir)
                        warnings.append(f"{rel_path}: {warning}")
                except (OSError, UnicodeDecodeError):
                    continue

        return warnings

    def regenerate_baseline(self) -> dict[str, str]:
        """Generate a new baseline from current source files.

        Saves to user_baseline if configured.

        Returns:
            Dictionary of file hashes.
        """
        hashes = compute_directory_hashes(self.source_dir, "**/*.py")

        if self.user_baseline:
            save_baseline(hashes, self.user_baseline)

        return hashes
