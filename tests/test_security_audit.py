# tests/test_security_audit.py
"""Tests for dependency CVE auditing."""

import pytest
from unittest.mock import patch, MagicMock

# Check if required dependencies are available
try:
    from merkaba.security.audit import scan_dependencies, CVEIssue
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    scan_dependencies = None
    CVEIssue = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestDependencyAudit:
    def test_scan_returns_list_of_cve_issues(self):
        """Should parse pip-audit output into CVEIssue objects."""
        mock_output = """[
            {
                "name": "requests",
                "version": "2.25.0",
                "vulns": [
                    {
                        "id": "CVE-2023-32681",
                        "fix_versions": ["2.31.0"],
                        "description": "Proxy-Authorization header leak"
                    }
                ]
            }
        ]"""

        with patch("merkaba.security.audit._run_pip_audit") as mock_run:
            mock_run.return_value = mock_output

            result = scan_dependencies()

        assert len(result) == 1
        assert result[0].package == "requests"
        assert result[0].cve_id == "CVE-2023-32681"
        assert result[0].fix_version == "2.31.0"

    def test_scan_handles_no_vulnerabilities(self):
        """Should return empty list when no CVEs found."""
        with patch("merkaba.security.audit._run_pip_audit") as mock_run:
            mock_run.return_value = "[]"

            result = scan_dependencies()

        assert result == []
