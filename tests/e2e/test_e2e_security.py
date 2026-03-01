# tests/e2e/test_e2e_security.py
"""End-to-end tests for the security status CLI command.

Uses real SQLite databases (in temp dirs) and real CLI invocations.
The keyring (get_secret) is mocked to avoid OS keychain access.
"""

import io
import json
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# 1. Defaults — no secrets configured
# ---------------------------------------------------------------------------

def test_security_status_defaults(cli_runner):
    """No secrets in keychain, no custom config — shows Disabled for both,
    default thresholds (3, 5 approvals per 60s)."""
    runner, app = cli_runner

    with patch("merkaba.security.secrets.get_secret", return_value=None):
        result = runner.invoke(app, ["security", "status"])

    assert result.exit_code == 0
    assert "2FA" in result.output
    assert "Disabled" in result.output
    assert "Encryption" in result.output
    assert "TOTP threshold: autonomy_level >= 3" in result.output
    assert "Rate limit: 5 approvals per 60s" in result.output


# ---------------------------------------------------------------------------
# 2. 2FA enabled
# ---------------------------------------------------------------------------

def test_security_status_2fa_enabled(cli_runner):
    """TOTP secret present in keychain — 2FA shows Enabled,
    encryption still Disabled."""
    runner, app = cli_runner

    def mock_get_secret(key):
        if key == "totp_secret":
            return "JBSWY3DPEHPK3PXP"
        return None

    with patch("merkaba.security.secrets.get_secret", side_effect=mock_get_secret):
        result = runner.invoke(app, ["security", "status"])

    assert result.exit_code == 0
    assert "2FA" in result.output
    assert "Enabled" in result.output
    # Encryption should still be disabled
    assert "Encryption" in result.output
    # Verify the Disabled is associated with encryption (appears after Encryption line)
    lines = result.output.strip().splitlines()
    encryption_line = [l for l in lines if "Encryption" in l][0]
    assert "Disabled" in encryption_line


# ---------------------------------------------------------------------------
# 3. Encryption enabled
# ---------------------------------------------------------------------------

def test_security_status_encryption_enabled(cli_runner):
    """Encryption key present in keychain — Encryption shows Enabled,
    2FA still Disabled."""
    runner, app = cli_runner

    def mock_get_secret(key):
        if key == "conversation_encryption_key":
            return "supersecretencryptionkey"
        return None

    with patch("merkaba.security.secrets.get_secret", side_effect=mock_get_secret):
        result = runner.invoke(app, ["security", "status"])

    assert result.exit_code == 0
    # 2FA should be disabled
    lines = result.output.strip().splitlines()
    tfa_line = [l for l in lines if "2FA" in l][0]
    assert "Disabled" in tfa_line
    # Encryption should be enabled
    encryption_line = [l for l in lines if "Encryption" in l][0]
    assert "Enabled" in encryption_line


# ---------------------------------------------------------------------------
# 4. Custom config — non-default thresholds
# ---------------------------------------------------------------------------

def test_security_status_custom_config(cli_runner):
    """Custom security config — verify custom thresholds appear in output."""
    runner, app = cli_runner

    config = {
        "security": {
            "totp_threshold": 5,
            "approval_rate_limit": {
                "max_approvals": 10,
                "window_seconds": 120,
            },
        }
    }

    with patch("merkaba.security.secrets.get_secret", return_value=None):
        real_open = open

        def mock_open(path, *args, **kwargs):
            if isinstance(path, str) and path.endswith("merkaba/config.json"):
                return io.StringIO(json.dumps(config))
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            result = runner.invoke(app, ["security", "status"])

    assert result.exit_code == 0
    assert "TOTP threshold: autonomy_level >= 5" in result.output
    assert "Rate limit: 10 approvals per 120s" in result.output
