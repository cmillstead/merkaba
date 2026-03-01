# tests/test_cli_security.py
"""Tests for security CLI commands (encryption, scan)."""

import sys
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

# Ensure ollama is mocked before merkaba imports (conftest installs one with proper
# exception classes; setdefault avoids overwriting it).
sys.modules.setdefault("ollama", MagicMock())

from merkaba.cli import app

runner = CliRunner()


class TestEnableEncryption:

    def test_enable_encryption_stores_key(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None
            result = runner.invoke(
                app,
                ["security", "enable-encryption"],
                input="my-passphrase\nmy-passphrase\n",
            )
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()
        mock_keyring.set_password.assert_called_once()

    def test_enable_encryption_rejects_mismatch(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None
            result = runner.invoke(
                app,
                ["security", "enable-encryption"],
                input="pass1\npass2\n",
            )
        assert result.exit_code != 0 or "do not match" in result.output.lower()

    def test_enable_encryption_already_configured(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "existing-key"
            result = runner.invoke(app, ["security", "enable-encryption"])
        assert "already" in result.output.lower()

    def test_disable_encryption_removes_key(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = "some-key"
            result = runner.invoke(
                app,
                ["security", "disable-encryption", "--yes"],
            )
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()
        mock_keyring.delete_password.assert_called_once()

    def test_disable_encryption_when_not_configured(self, tmp_path):
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None
            result = runner.invoke(app, ["security", "disable-encryption", "--yes"])
        assert "not configured" in result.output.lower()

    def test_encryption_status_shown_in_security_status(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text("{}")
        with patch("merkaba.cli.MERKABA_DIR", str(tmp_path)), \
             patch("merkaba.security.secrets.keyring") as mock_keyring, \
             patch("os.path.expanduser", return_value=str(config_path)):
            mock_keyring.get_password.side_effect = lambda svc, key: "key" if key == "conversation_encryption_key" else None
            result = runner.invoke(app, ["security", "status"])
        assert "encryption" in result.output.lower()


class TestSecurityScan:

    def test_quick_scan_no_issues(self):
        from merkaba.security.scanner import SecurityReport

        report = SecurityReport()
        with patch("merkaba.security.scanner.SecurityScanner.quick_scan", return_value=report):
            result = runner.invoke(app, ["security", "scan"])
        assert result.exit_code == 0
        assert "No issues found" in result.output

    def test_full_scan_no_issues(self):
        from merkaba.security.scanner import SecurityReport

        report = SecurityReport()
        with patch("merkaba.security.scanner.SecurityScanner.full_scan", return_value=report):
            result = runner.invoke(app, ["security", "scan", "--full"])
        assert result.exit_code == 0
        assert "full" in result.output.lower()

    def test_quick_scan_with_integrity_issues(self):
        from merkaba.security.scanner import SecurityReport

        report = SecurityReport(integrity_issues=["security/permissions.py modified"])
        with patch("merkaba.security.scanner.SecurityScanner.quick_scan", return_value=report):
            result = runner.invoke(app, ["security", "scan"])
        assert result.exit_code == 1
        assert "permissions.py modified" in result.output

    def test_full_scan_with_cve_issues(self):
        from merkaba.security.scanner import SecurityReport
        from merkaba.security.audit import CVEIssue

        cve = CVEIssue(
            package="requests",
            version="2.28.0",
            cve_id="CVE-2023-1234",
            description="Test vulnerability",
            fix_version="2.31.0",
        )
        report = SecurityReport(cve_issues=[cve])
        with patch("merkaba.security.scanner.SecurityScanner.full_scan", return_value=report):
            result = runner.invoke(app, ["security", "scan", "--full"])
        assert result.exit_code == 1
        assert "CVE-2023-1234" in result.output
        assert "requests" in result.output

    def test_full_scan_with_code_warnings(self):
        from merkaba.security.scanner import SecurityReport

        report = SecurityReport(code_warnings=["agent.py: dangerous pattern detected"])
        with patch("merkaba.security.scanner.SecurityScanner.full_scan", return_value=report):
            result = runner.invoke(app, ["security", "scan", "--full"])
        assert result.exit_code == 1
        assert "dangerous pattern" in result.output

    def test_regenerate_baseline(self):
        with patch("merkaba.security.scanner.SecurityScanner.regenerate_baseline", return_value={"a.py": "abc123"}):
            result = runner.invoke(app, ["security", "scan", "--regenerate-baseline"])
        assert result.exit_code == 0
        assert "1 file(s)" in result.output
