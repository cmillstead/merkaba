# tests/test_cli_pairing.py
"""Tests for CLI pairing commands (pair list, initiate, confirm, revoke)."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

# Ensure ollama is mocked before merkaba imports.
sys.modules.setdefault("ollama", MagicMock())

from merkaba.cli import app

runner = CliRunner()


class TestPairList:

    def test_list_empty(self):
        """No paired identities shows dim message."""
        with patch("merkaba.security.pairing.GatewayPairing.list_paired", return_value=[]):
            result = runner.invoke(app, ["pair", "list"])
        assert result.exit_code == 0
        assert "no paired" in result.output.lower()

    def test_list_with_identities(self):
        """Paired identities are shown in a table."""
        with patch("merkaba.security.pairing.GatewayPairing.list_paired",
                    return_value=["discord:alice", "telegram:bob"]):
            result = runner.invoke(app, ["pair", "list"])
        assert result.exit_code == 0
        assert "discord:alice" in result.output
        assert "telegram:bob" in result.output
        assert "Paired Identities" in result.output


class TestPairInitiate:

    def test_initiate_generates_code(self):
        """Initiate returns a 6-char code and instructions."""
        with patch("merkaba.security.pairing.GatewayPairing.initiate", return_value="ABC123"):
            result = runner.invoke(app, ["pair", "initiate", "telegram", "tg:user1"])
        assert result.exit_code == 0
        assert "ABC123" in result.output
        assert "tg:user1" in result.output
        assert "telegram" in result.output
        assert "merkaba pair confirm" in result.output

    def test_initiate_shows_expiry(self):
        """Initiate mentions code expiry."""
        with patch("merkaba.security.pairing.GatewayPairing.initiate", return_value="XYZ789"):
            result = runner.invoke(app, ["pair", "initiate", "discord", "dc:user2"])
        assert result.exit_code == 0
        assert "expires" in result.output.lower()


class TestPairConfirm:

    def test_confirm_valid_code(self):
        """Valid code confirms pairing."""
        with patch("merkaba.security.pairing.GatewayPairing.confirm", return_value=True):
            result = runner.invoke(app, ["pair", "confirm", "tg:user1", "ABC123"])
        assert result.exit_code == 0
        assert "paired successfully" in result.output.lower()
        assert "tg:user1" in result.output

    def test_confirm_invalid_code(self):
        """Invalid code reports failure with exit code 1."""
        with patch("merkaba.security.pairing.GatewayPairing.confirm", return_value=False):
            result = runner.invoke(app, ["pair", "confirm", "tg:user1", "WRONG1"])
        assert result.exit_code == 1
        assert "failed" in result.output.lower()

    def test_confirm_missing_args(self):
        """Missing arguments produce an error."""
        result = runner.invoke(app, ["pair", "confirm"])
        assert result.exit_code != 0


class TestPairRevoke:

    def test_revoke_paired_identity(self):
        """Revoking a paired identity shows success."""
        with patch("merkaba.security.pairing.GatewayPairing.is_paired", return_value=True), \
             patch("merkaba.security.pairing.GatewayPairing.revoke") as mock_revoke:
            result = runner.invoke(app, ["pair", "revoke", "tg:user1"])
        assert result.exit_code == 0
        assert "revoked" in result.output.lower()
        assert "tg:user1" in result.output
        mock_revoke.assert_called_once_with("tg:user1")

    def test_revoke_unknown_identity(self):
        """Revoking a non-paired identity shows a warning."""
        with patch("merkaba.security.pairing.GatewayPairing.is_paired", return_value=False):
            result = runner.invoke(app, ["pair", "revoke", "unknown:user"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestPairIntegration:
    """Tests using real GatewayPairing (no mocks) to verify end-to-end flow."""

    def test_full_pairing_flow(self):
        """Initiate then confirm with the same GatewayPairing instance works."""
        from merkaba.security.pairing import GatewayPairing

        gp = GatewayPairing()
        # Simulate: initiate, get code, then confirm
        code = gp.initiate("telegram", "tg:user1")
        assert gp.confirm("tg:user1", code)
        assert gp.is_paired("tg:user1")

        # Verify list
        paired = gp.list_paired()
        assert "tg:user1" in paired

        # Revoke
        gp.revoke("tg:user1")
        assert not gp.is_paired("tg:user1")
        assert gp.list_paired() == []

    def test_pair_help(self):
        """Pair group shows help text."""
        result = runner.invoke(app, ["pair", "--help"])
        assert result.exit_code == 0
        assert "pairing" in result.output.lower()
