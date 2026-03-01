# tests/test_security_scanner_extended.py
"""Extended tests for security/scanner.py — untested branches using real files."""

import json
from pathlib import Path

import pytest

from merkaba.security.scanner import SecurityScanner, SecurityReport
from merkaba.security.integrity import (
    compute_directory_hashes,
    save_baseline,
    load_baseline,
)


class TestIntegrityScanner:
    def test_no_baseline_returns_no_integrity_issues(self, tmp_path):
        """Without baseline files, _check_integrity returns empty list."""
        scanner = SecurityScanner(source_dir=tmp_path)
        report = scanner.quick_scan()
        assert report.integrity_issues == []

    def test_quick_scan_with_matching_baseline(self, tmp_path):
        """Matching baseline should produce no issues for quick scan."""
        # Create a security file that matches CORE_SECURITY_FILES
        sec_dir = tmp_path / "security"
        sec_dir.mkdir()
        (sec_dir / "permissions.py").write_text("# permissions")

        # Generate and save baseline
        hashes = compute_directory_hashes(tmp_path, "**/*.py")
        baseline_path = tmp_path / "baseline.json"
        save_baseline(hashes, baseline_path)

        scanner = SecurityScanner(
            source_dir=tmp_path,
            user_baseline=baseline_path,
        )
        report = scanner.quick_scan()
        assert report.integrity_issues == []

    def test_quick_scan_detects_modified_file(self, tmp_path):
        """Modified file after baseline should be reported."""
        sec_dir = tmp_path / "security"
        sec_dir.mkdir()
        target = sec_dir / "permissions.py"
        target.write_text("# original")

        hashes = compute_directory_hashes(tmp_path, "**/*.py")
        baseline_path = tmp_path / "baseline.json"
        save_baseline(hashes, baseline_path)

        # Modify the file
        target.write_text("# modified content")

        scanner = SecurityScanner(
            source_dir=tmp_path,
            user_baseline=baseline_path,
        )
        report = scanner.quick_scan()
        assert any("modified" in issue for issue in report.integrity_issues)

    def test_full_scan_detects_added_file(self, tmp_path):
        """File added after baseline should be reported."""
        (tmp_path / "original.py").write_text("# original")

        hashes = compute_directory_hashes(tmp_path, "**/*.py")
        baseline_path = tmp_path / "baseline.json"
        save_baseline(hashes, baseline_path)

        # Add a new file
        (tmp_path / "new_file.py").write_text("# new")

        scanner = SecurityScanner(
            source_dir=tmp_path,
            user_baseline=baseline_path,
        )
        report = scanner.full_scan()
        assert any("added" in issue for issue in report.integrity_issues)

    def test_full_scan_detects_removed_file(self, tmp_path):
        """File removed after baseline should be reported."""
        target = tmp_path / "removeme.py"
        target.write_text("# will be removed")

        hashes = compute_directory_hashes(tmp_path, "**/*.py")
        baseline_path = tmp_path / "baseline.json"
        save_baseline(hashes, baseline_path)

        # Remove the file
        target.unlink()

        scanner = SecurityScanner(
            source_dir=tmp_path,
            user_baseline=baseline_path,
        )
        report = scanner.full_scan()
        assert any("removed" in issue for issue in report.integrity_issues)


class TestSelfScan:
    def test_detects_dangerous_pattern(self, tmp_path):
        """A .py file with dangerous code pattern should produce a warning."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("import subprocess\nsubprocess.run(['rm', '-rf', '/'])")

        scanner = SecurityScanner(source_dir=tmp_path)
        report = scanner.full_scan()
        assert len(report.code_warnings) > 0
        assert any("subprocess" in w for w in report.code_warnings)

    def test_clean_file_no_warnings(self, tmp_path):
        """A clean .py file should produce no code warnings."""
        clean_file = tmp_path / "clean.py"
        clean_file.write_text("def hello():\n    return 'world'\n")

        scanner = SecurityScanner(source_dir=tmp_path)
        report = scanner.full_scan()
        assert report.code_warnings == []


class TestSecurityReportSummary:
    def test_clean_report_summary(self):
        """Clean report should say 'No issues found.'"""
        report = SecurityReport()
        summary = report.summary()
        assert "No issues found." in summary

    def test_issues_report_summary(self):
        """Report with issues should format all sections."""
        from merkaba.security.audit import CVEIssue
        report = SecurityReport(
            integrity_issues=["file.py modified"],
            cve_issues=[CVEIssue(
                package="requests",
                version="2.25.0",
                cve_id="CVE-2023-32681",
                description="leak",
                fix_version="2.31.0",
            )],
            code_warnings=["bad.py: dangerous pattern"],
        )
        summary = report.summary()
        assert "Integrity Issues (1)" in summary
        assert "file.py modified" in summary
        assert "CVE Issues (1)" in summary
        assert "CVE-2023-32681" in summary
        assert "Fix available: 2.31.0" in summary
        assert "Code Warnings (1)" in summary
        assert "bad.py: dangerous pattern" in summary
