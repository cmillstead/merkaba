# tests/e2e/test_e2e_cli_basics.py
"""End-to-end tests for CLI basics: --verbose flag, --version output, exit code constants.

Uses the CliRunner in-process for quick, isolated checks that do not require
real databases or LLM connections.
"""

import sys
import platform

import pytest
from typer.testing import CliRunner

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# 1. Exit code constants
# ---------------------------------------------------------------------------

def test_exit_codes_exist():
    """EXIT_OK, EXIT_ERROR, EXIT_CONFIG, EXIT_NOT_FOUND are importable integers."""
    from merkaba.cli import EXIT_OK, EXIT_ERROR, EXIT_CONFIG, EXIT_NOT_FOUND

    assert EXIT_OK == 0
    assert EXIT_ERROR == 1
    assert EXIT_CONFIG == 2
    assert EXIT_NOT_FOUND == 3
    # All must be plain ints
    assert isinstance(EXIT_OK, int)
    assert isinstance(EXIT_ERROR, int)
    assert isinstance(EXIT_CONFIG, int)
    assert isinstance(EXIT_NOT_FOUND, int)


# ---------------------------------------------------------------------------
# 2. --verbose / -V flag
# ---------------------------------------------------------------------------

def test_verbose_flag_long(patched_dbs):
    """--verbose flag is accepted and does not crash the CLI."""
    from merkaba.cli import app

    runner = _make_runner()
    # Run a cheap sub-command (status) with --verbose to exercise the flag
    # without needing an LLM or real databases.
    from unittest.mock import patch
    with (
        patch("urllib.request.urlopen", side_effect=OSError("offline")),
    ):
        result = runner.invoke(app, ["--verbose", "status"])

    # The command itself may fail for other reasons but the flag must be
    # accepted — an unrecognised flag would produce exit code 2 with
    # "No such option" in output.
    assert "No such option" not in (result.output or "")
    assert result.exit_code != 2 or "No such option" not in (result.output or "")


def test_verbose_flag_short(patched_dbs):
    """-V shorthand is accepted and does not crash the CLI."""
    from merkaba.cli import app

    runner = _make_runner()
    from unittest.mock import patch
    with (
        patch("urllib.request.urlopen", side_effect=OSError("offline")),
    ):
        result = runner.invoke(app, ["-V", "status"])

    assert "No such option" not in (result.output or "")


def test_verbose_sets_module_flag(patched_dbs):
    """After invoking with --verbose the module-level 'verbose' variable is True."""
    import merkaba.cli as cli_module
    from merkaba.cli import app

    runner = _make_runner()
    from unittest.mock import patch
    with (
        patch("urllib.request.urlopen", side_effect=OSError("offline")),
    ):
        runner.invoke(app, ["--verbose", "status"])

    assert cli_module.verbose is True

    # Restore for other tests (runner invocations share the same module state)
    runner.invoke(app, ["status"])
    # verbose resets to False when the flag is omitted
    assert cli_module.verbose is False


# ---------------------------------------------------------------------------
# 3. --version output includes Python version and platform
# ---------------------------------------------------------------------------

def test_version_shows_version_string():
    """--version prints the merkaba version number."""
    from merkaba.cli import app
    from merkaba import __version__

    runner = _make_runner()
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_version_shows_python_version():
    """--version output includes the running Python version."""
    from merkaba.cli import app

    runner = _make_runner()
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    py = sys.version_info
    expected_py = f"Python {py.major}.{py.minor}.{py.micro}"
    assert expected_py in result.output


def test_version_shows_platform():
    """--version output includes the OS/platform name and machine architecture."""
    from merkaba.cli import app

    runner = _make_runner()
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert platform.system() in result.output
    assert platform.machine() in result.output


# ---------------------------------------------------------------------------
# 4. Config error uses EXIT_CONFIG (exit code 2)
# ---------------------------------------------------------------------------

def test_chat_config_error_uses_exit_config(patched_dbs):
    """When config has errors the chat command exits with EXIT_CONFIG (2), not 1."""
    from merkaba.cli import app, EXIT_CONFIG
    from merkaba.config.validation import ConfigIssue, Severity
    from unittest.mock import patch

    error_issue = ConfigIssue(
        severity=Severity.ERROR,
        component="test",
        message="Intentional test error",
        hint=None,
    )

    runner = _make_runner()
    with (
        patch("merkaba.config.validation.validate_config", return_value=[error_issue]),
        patch("merkaba.config.validation.print_startup_report"),
    ):
        result = runner.invoke(app, ["chat", "hello"])

    assert result.exit_code == EXIT_CONFIG
