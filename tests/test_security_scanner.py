# tests/test_security_scanner.py
"""Tests for security scanner orchestration."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Check if required dependencies are available
try:
    from merkaba.security.scanner import SecurityScanner, SecurityReport
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    SecurityScanner = None
    SecurityReport = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestSecurityScanner:
    def test_quick_scan_checks_core_files(self, tmp_path):
        """Quick scan should only check security-critical files."""
        scanner = SecurityScanner(source_dir=tmp_path)

        with patch.object(scanner, "_check_integrity") as mock_integrity:
            mock_integrity.return_value = []

            report = scanner.quick_scan()

        mock_integrity.assert_called_once()

    def test_full_scan_runs_all_checks(self, tmp_path):
        """Full scan should run integrity, audit, and self-scan."""
        scanner = SecurityScanner(source_dir=tmp_path)

        with patch.object(scanner, "_check_integrity") as mock_int, \
             patch.object(scanner, "_scan_dependencies") as mock_deps, \
             patch.object(scanner, "_self_scan") as mock_self:
            mock_int.return_value = []
            mock_deps.return_value = []
            mock_self.return_value = []

            report = scanner.full_scan()

        mock_int.assert_called_once()
        mock_deps.assert_called_once()
        mock_self.assert_called_once()

    def test_report_has_issues_when_problems_found(self):
        """Report should indicate issues exist."""
        report = SecurityReport(
            integrity_issues=["file.py modified"],
            cve_issues=[],
            code_warnings=[],
        )

        assert report.has_issues is True
