# tests/test_cli_integrations.py
import sys
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

try:
    import keyring.errors
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_DEPS, reason="Missing keyring")

# Mock problematic modules before importing merkaba.cli
for _mod in ("ollama", "telegram", "telegram.ext"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from merkaba.cli import app

runner = CliRunner()


def test_integrations_list():
    result = runner.invoke(app, ["integrations", "list"])
    assert result.exit_code == 0
    assert "email" in result.output
    assert "stripe" in result.output
    assert "etsy" in result.output


def test_integrations_test_success(mocker):
    stored = {
        ("merkaba-ai", "integration:stripe:api_key"): "sk_test_fake",
    }
    mocker.patch(
        "merkaba.security.secrets.keyring.get_password",
        side_effect=lambda svc, key: stored.get((svc, key)),
    )
    mocker.patch("stripe.Balance.retrieve", return_value=MagicMock(
        available=[MagicMock(amount=0, currency="usd")]
    ))

    result = runner.invoke(app, ["integrations", "test", "stripe"])
    assert result.exit_code == 0
    # Should show success indicator
    assert "pass" in result.output.lower() or "✓" in result.output


def test_integrations_test_unknown_adapter():
    result = runner.invoke(app, ["integrations", "test", "nonexistent_xyz"])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()
