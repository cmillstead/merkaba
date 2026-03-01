# tests/test_cli_plugins.py
"""Tests for plugin CLI commands."""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock

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


class TestPluginListCommand:
    """Tests for merkaba plugins list."""

    @patch("merkaba.cli.PluginRegistry")
    def test_plugins_list_shows_skills(self, mock_registry):
        """plugins list should show loaded skills."""
        mock_instance = MagicMock()
        mock_instance.skills.list_skills.return_value = ["brainstorming", "tdd"]
        mock_instance.commands.list_commands.return_value = ["commit"]
        mock_instance.agents.list_agents.return_value = []
        mock_instance.hooks.hooks = []
        mock_registry.default.return_value = mock_instance

        result = runner.invoke(app, ["plugins", "list"])

        assert result.exit_code == 0
        assert "brainstorming" in result.output
        assert "tdd" in result.output
        assert "commit" in result.output


class TestCommandsListCommand:
    """Tests for merkaba commands list."""

    @patch("merkaba.cli.PluginRegistry")
    def test_commands_list_shows_commands(self, mock_registry):
        """commands list should show available commands."""
        mock_instance = MagicMock()
        mock_instance.commands.list_commands.return_value = ["commit", "review-pr"]
        mock_registry.default.return_value = mock_instance

        result = runner.invoke(app, ["commands", "list"])

        assert result.exit_code == 0
        assert "commit" in result.output
        assert "review-pr" in result.output


class TestPluginImportCommand:
    """Tests for merkaba plugins import."""

    def test_import_command_exists(self):
        """plugins import --help should work."""
        result = runner.invoke(app, ["plugins", "import", "--help"])
        assert result.exit_code == 0
        assert "import" in result.stdout.lower()

    @patch("merkaba.cli.PluginImporter")
    def test_import_skill_success(self, mock_importer_class):
        """plugins import should import a skill successfully."""
        from merkaba.plugins.importer import ImportResult

        mock_result = ImportResult(
            skill_name="test-skill",
            success=True,
            compatibility=100,
            conversion="rule_based",
        )

        mock_importer = MagicMock()
        mock_importer.import_skill.return_value = mock_result
        mock_importer_class.return_value = mock_importer

        result = runner.invoke(app, ["plugins", "import", "test-plugin:test-skill"])

        assert result.exit_code == 0
        assert "100%" in result.stdout or "test-skill" in result.stdout

    @patch("merkaba.cli.PluginImporter")
    def test_import_skill_skipped(self, mock_importer_class):
        """plugins import should show skipped skills."""
        from merkaba.plugins.importer import ImportResult

        mock_result = ImportResult(
            skill_name="low-compat-skill",
            success=False,
            skipped=True,
            compatibility=30,
            missing_tools={"TaskAgent", "Browser"},
        )

        mock_importer = MagicMock()
        mock_importer.import_skill.return_value = mock_result
        mock_importer_class.return_value = mock_importer

        result = runner.invoke(app, ["plugins", "import", "test-plugin:low-compat-skill"])

        assert result.exit_code == 0
        assert "skipped" in result.stdout.lower() or "30%" in result.stdout

    @patch("merkaba.cli.PluginImporter")
    def test_import_skill_error(self, mock_importer_class):
        """plugins import should show errors."""
        from merkaba.plugins.importer import ImportResult

        mock_result = ImportResult(
            skill_name="missing-skill",
            success=False,
            error="Skill not found: test-plugin/missing-skill",
        )

        mock_importer = MagicMock()
        mock_importer.import_skill.return_value = mock_result
        mock_importer_class.return_value = mock_importer

        result = runner.invoke(app, ["plugins", "import", "test-plugin:missing-skill"])

        assert result.exit_code == 0
        assert "not found" in result.stdout.lower() or "missing-skill" in result.stdout

    def test_import_plugin_without_skill(self):
        """plugins import with just plugin name shows TODO message."""
        result = runner.invoke(app, ["plugins", "import", "test-plugin"])

        assert result.exit_code == 0
        assert "test-plugin" in result.stdout


class TestPluginAvailableCommand:
    """Tests for merkaba plugins available."""

    def test_available_command_exists(self):
        """plugins available --help should work."""
        result = runner.invoke(app, ["plugins", "available", "--help"])
        assert result.exit_code == 0

    def test_lists_claude_plugins(self, tmp_path):
        """plugins available should list Claude Code plugins."""
        # Create mock plugin structure: org/plugin/version/skills/skill-name/
        plugin = tmp_path / "claude-plugins-official" / "superpowers" / "1.0.0" / "skills" / "brainstorming"
        plugin.mkdir(parents=True)
        (plugin / "SKILL.md").write_text("---\nname: brainstorming\n---\n# Test")

        with patch("merkaba.cli.CLAUDE_PLUGIN_DIR", str(tmp_path)):
            result = runner.invoke(app, ["plugins", "available"])

        assert result.exit_code == 0
        assert "superpowers" in result.stdout or "brainstorming" in result.stdout

    def test_no_plugins_directory(self, tmp_path):
        """plugins available should handle missing plugin directory."""
        nonexistent = tmp_path / "nonexistent"

        with patch("merkaba.cli.CLAUDE_PLUGIN_DIR", str(nonexistent)):
            result = runner.invoke(app, ["plugins", "available"])

        assert result.exit_code == 0
        assert "No Claude Code plugins found" in result.stdout
