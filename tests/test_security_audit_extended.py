# tests/test_security_audit_extended.py
"""Extended tests for security/audit.py — untested branches."""

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from merkaba.security.audit import scan_dependencies, CVEIssue, _run_pip_audit


class TestRunPipAudit:
    def test_timeout_returns_empty_list(self):
        """subprocess.run raising TimeoutExpired should yield '[]'."""
        with patch("merkaba.security.audit.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pip-audit", timeout=120)
            result = _run_pip_audit()
        assert result == "[]"

    def test_pip_audit_not_installed(self):
        """FileNotFoundError (pip-audit missing) should yield '[]'."""
        with patch("merkaba.security.audit.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("No such file: pip-audit")
            result = _run_pip_audit()
        assert result == "[]"

    def test_timeout_value_passed(self):
        """Verify timeout=120 is passed to subprocess.run."""
        with patch("merkaba.security.audit.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="[]")
            _run_pip_audit()
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 120


class TestScanDependencies:
    def test_malformed_json_returns_empty(self):
        """Invalid JSON from pip-audit should return empty list."""
        with patch("merkaba.security.audit._run_pip_audit", return_value="NOT JSON!!!"):
            result = scan_dependencies()
        assert result == []

    def test_empty_vulns_list(self):
        """Package with 'vulns': [] should produce no CVEIssues."""
        data = json.dumps([{"name": "safe-pkg", "version": "1.0.0", "vulns": []}])
        with patch("merkaba.security.audit._run_pip_audit", return_value=data):
            result = scan_dependencies()
        assert result == []

    def test_multiple_packages_multiple_cves(self):
        """2 packages x 2 CVEs = 4 issues."""
        data = json.dumps([
            {
                "name": "pkg-a",
                "version": "1.0",
                "vulns": [
                    {"id": "CVE-A1", "fix_versions": ["1.1"], "description": "a1"},
                    {"id": "CVE-A2", "fix_versions": ["1.2"], "description": "a2"},
                ],
            },
            {
                "name": "pkg-b",
                "version": "2.0",
                "vulns": [
                    {"id": "CVE-B1", "fix_versions": [], "description": "b1"},
                    {"id": "CVE-B2", "fix_versions": ["2.1"], "description": "b2"},
                ],
            },
        ])
        with patch("merkaba.security.audit._run_pip_audit", return_value=data):
            result = scan_dependencies()
        assert len(result) == 4
        assert {r.cve_id for r in result} == {"CVE-A1", "CVE-A2", "CVE-B1", "CVE-B2"}

    def test_cve_issue_fields_populated(self):
        """Verify all CVEIssue fields are set correctly."""
        data = json.dumps([{
            "name": "requests",
            "version": "2.25.0",
            "vulns": [{
                "id": "CVE-2023-32681",
                "fix_versions": ["2.31.0"],
                "description": "Proxy-Authorization header leak",
            }],
        }])
        with patch("merkaba.security.audit._run_pip_audit", return_value=data):
            result = scan_dependencies()
        issue = result[0]
        assert issue.package == "requests"
        assert issue.version == "2.25.0"
        assert issue.cve_id == "CVE-2023-32681"
        assert issue.description == "Proxy-Authorization header leak"
        assert issue.fix_version == "2.31.0"
        assert issue.severity == "UNKNOWN"

    def test_fix_version_none_when_empty(self):
        """fix_versions=[] should yield fix_version=None."""
        data = json.dumps([{
            "name": "vuln-pkg",
            "version": "0.1",
            "vulns": [{"id": "CVE-999", "fix_versions": [], "description": "no fix"}],
        }])
        with patch("merkaba.security.audit._run_pip_audit", return_value=data):
            result = scan_dependencies()
        assert result[0].fix_version is None
