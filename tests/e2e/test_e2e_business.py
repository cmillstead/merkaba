# tests/e2e/test_e2e_business.py
"""End-to-end tests for business management CLI commands.

Uses real SQLite databases (in temp dirs) and real CLI invocations.
Only the LLM layer is mocked (via global conftest).
"""

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# 1. Add and list
# ---------------------------------------------------------------------------

def test_business_add_and_list(cli_runner):
    """Add a business, then list — it should appear in output."""
    runner, app = cli_runner

    result = runner.invoke(app, ["business", "add", "--name", "Widget Co", "--type", "ecommerce"])
    assert result.exit_code == 0
    assert "created" in result.output.lower()
    assert "Widget Co" in result.output

    result = runner.invoke(app, ["business", "list"])
    assert result.exit_code == 0
    assert "Widget Co" in result.output


# ---------------------------------------------------------------------------
# 2. Add multiple types
# ---------------------------------------------------------------------------

def test_business_add_multiple_types(cli_runner):
    """Add ecommerce, content, and saas businesses — list shows all three."""
    runner, app = cli_runner

    for name, biz_type in [("Shop", "ecommerce"), ("Blog", "content"), ("Platform", "saas")]:
        result = runner.invoke(app, ["business", "add", "--name", name, "--type", biz_type])
        assert result.exit_code == 0

    result = runner.invoke(app, ["business", "list"])
    assert result.exit_code == 0
    assert "Shop" in result.output
    assert "Blog" in result.output
    assert "Platform" in result.output


# ---------------------------------------------------------------------------
# 3. Show details
# ---------------------------------------------------------------------------

def test_business_show_details(cli_runner):
    """Add a business, then show it — verify name and type in output."""
    runner, app = cli_runner

    runner.invoke(app, ["business", "add", "--name", "Detail Shop", "--type", "ecommerce"])

    result = runner.invoke(app, ["business", "show", "1"])
    assert result.exit_code == 0
    assert "Detail Shop" in result.output
    assert "ecommerce" in result.output


# ---------------------------------------------------------------------------
# 4. Show not found
# ---------------------------------------------------------------------------

def test_business_show_not_found(cli_runner):
    """Show a non-existent business ID — should exit with code 1."""
    runner, app = cli_runner

    result = runner.invoke(app, ["business", "show", "999"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# 5. Update name
# ---------------------------------------------------------------------------

def test_business_update_name(cli_runner):
    """Add a business, update its name, verify via show."""
    runner, app = cli_runner

    runner.invoke(app, ["business", "add", "--name", "Old Name", "--type", "ecommerce"])

    result = runner.invoke(app, ["business", "update", "1", "--name", "New Name"])
    assert result.exit_code == 0
    assert "updated" in result.output.lower()

    result = runner.invoke(app, ["business", "show", "1"])
    assert result.exit_code == 0
    assert "New Name" in result.output


# ---------------------------------------------------------------------------
# 6. Update autonomy
# ---------------------------------------------------------------------------

def test_business_update_autonomy(cli_runner):
    """Add a business with default autonomy, update it, verify via show."""
    runner, app = cli_runner

    runner.invoke(app, ["business", "add", "--name", "Auto Shop", "--type", "ecommerce", "--autonomy", "1"])

    result = runner.invoke(app, ["business", "update", "1", "--autonomy", "4"])
    assert result.exit_code == 0
    assert "updated" in result.output.lower()

    result = runner.invoke(app, ["business", "show", "1"])
    assert result.exit_code == 0
    assert "4" in result.output


# ---------------------------------------------------------------------------
# 7. Dashboard
# ---------------------------------------------------------------------------

def test_business_dashboard(cli_runner):
    """Add a business, open dashboard — verify output contains business info."""
    runner, app = cli_runner

    runner.invoke(app, ["business", "add", "--name", "Dash Corp", "--type", "saas"])

    result = runner.invoke(app, ["business", "dashboard", "1"])
    assert result.exit_code == 0
    assert "Dash Corp" in result.output
    assert "saas" in result.output


# ---------------------------------------------------------------------------
# 8. Business isolation
# ---------------------------------------------------------------------------

def test_business_isolation(cli_runner):
    """Add two businesses — show for each returns only its own data."""
    runner, app = cli_runner

    runner.invoke(app, ["business", "add", "--name", "Alpha Inc", "--type", "ecommerce"])
    runner.invoke(app, ["business", "add", "--name", "Beta LLC", "--type", "content"])

    result_alpha = runner.invoke(app, ["business", "show", "1"])
    assert result_alpha.exit_code == 0
    assert "Alpha Inc" in result_alpha.output
    assert "Beta LLC" not in result_alpha.output

    result_beta = runner.invoke(app, ["business", "show", "2"])
    assert result_beta.exit_code == 0
    assert "Beta LLC" in result_beta.output
    assert "Alpha Inc" not in result_beta.output
