import pytest
from unittest.mock import patch

from typer.testing import CliRunner

# Check if required dependencies are available
try:
    from merkaba.cli import app
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    app = None

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


def test_cli_has_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "merkaba" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_cli_chat_uses_agent():
    """Test that chat command invokes the agent."""
    with patch("merkaba.agent.Agent") as mock_agent:
        mock_instance = mock_agent.return_value
        mock_instance.run.return_value = "Hello from Merkaba!"

        result = runner.invoke(app, ["chat", "Hello"])

        assert result.exit_code == 0
        mock_agent.assert_called_once_with(model="qwen3.5:122b")
        mock_instance.run.assert_called_once_with("Hello")


def test_cli_chat_uses_custom_model():
    """Test that chat command passes custom model to agent."""
    with patch("merkaba.agent.Agent") as mock_agent:
        mock_instance = mock_agent.return_value
        mock_instance.run.return_value = "Hello from Merkaba!"

        result = runner.invoke(app, ["chat", "--model", "llama3", "Hello"])

        assert result.exit_code == 0
        mock_agent.assert_called_once_with(model="llama3")
        mock_instance.run.assert_called_once_with("Hello")


def test_cli_chat_interactive_exit():
    """Test interactive mode exit command."""
    with patch("merkaba.agent.Agent"):
        result = runner.invoke(app, ["chat"], input="exit\n")
        assert result.exit_code == 0
        assert "Goodbye!" in result.stdout
