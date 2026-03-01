# tests/e2e/test_e2e_plugins.py
"""End-to-end tests for the plugin import cycle.

Covers: list, available, import, and uninstall CLI commands.
Uses real CLI invocations with temp directories and patched paths.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_fake_plugin(base_dir, org="testorg", plugin="testplugin", version="1.0.0", skill_name="test-skill"):
    """Create a minimal fake plugin directory structure."""
    skill_dir = base_dir / org / plugin / version / "skills" / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\nTest skill content."
    )
    return skill_dir


# ---------------------------------------------------------------------------
# 1. List — empty registry
# ---------------------------------------------------------------------------

def test_plugins_list_empty(cli_runner):
    """With empty/nonexistent plugin dirs, 'plugins list' shows 'No skills loaded'."""
    runner, app = cli_runner

    mock_registry = MagicMock()
    mock_registry.skills.list_skills.return_value = []
    mock_registry.commands.list_commands.return_value = []
    mock_registry.agents.list_agents.return_value = []
    mock_registry.hooks.hooks = []

    with patch("merkaba.plugins.PluginRegistry.default", return_value=mock_registry):
        result = runner.invoke(app, ["plugins", "list"])

    assert result.exit_code == 0
    assert "No skills loaded" in result.output


# ---------------------------------------------------------------------------
# 2. Available — empty plugin dir
# ---------------------------------------------------------------------------

def test_plugins_available_empty(cli_runner, tmp_path):
    """No plugins in CLAUDE_PLUGIN_DIR shows 'No Claude Code plugins found'."""
    runner, app = cli_runner

    empty_dir = tmp_path / "empty_plugins"
    # Intentionally do NOT create the directory — tests the non-existent path

    with patch("merkaba.cli.CLAUDE_PLUGIN_DIR", str(empty_dir)):
        result = runner.invoke(app, ["plugins", "available"])

    assert result.exit_code == 0
    assert "No Claude Code plugins found" in result.output


# ---------------------------------------------------------------------------
# 3. Available — with a plugin present
# ---------------------------------------------------------------------------

def test_plugins_available_with_plugin(cli_runner, tmp_path):
    """Create a fake plugin and verify its name appears in 'plugins available'."""
    runner, app = cli_runner

    plugin_cache = tmp_path / "plugin_cache"
    plugin_cache.mkdir()
    _create_fake_plugin(plugin_cache, org="myorg", plugin="cool-plugin", skill_name="greet")

    with patch("merkaba.cli.CLAUDE_PLUGIN_DIR", str(plugin_cache)):
        result = runner.invoke(app, ["plugins", "available"])

    assert result.exit_code == 0
    assert "cool-plugin" in result.output
    assert "greet" in result.output


# ---------------------------------------------------------------------------
# 4. Import — single skill
# ---------------------------------------------------------------------------

def test_plugins_import_skill(cli_runner, tmp_path):
    """Import a single skill from a fake plugin and verify success message."""
    runner, app = cli_runner

    source_dir = tmp_path / "source_cache"
    source_dir.mkdir()
    _create_fake_plugin(source_dir, org="acme", plugin="widgets", skill_name="spin")

    dest_dir = tmp_path / "merkaba_plugins"
    dest_dir.mkdir()

    with patch("merkaba.cli.os.path.expanduser") as mock_expand:
        def _expand(path):
            if path == "~/.claude/plugins/cache":
                return str(source_dir)
            if path == "~/.merkaba/plugins":
                return str(dest_dir)
            # Fall through for any other paths
            from os.path import expanduser as real_expand
            return real_expand(path)

        mock_expand.side_effect = _expand
        result = runner.invoke(app, ["plugins", "import", "widgets:spin"])

    assert result.exit_code == 0
    assert "spin" in result.output
    assert "compatible" in result.output

    # Verify the skill was actually written to the dest dir
    imported_skill = dest_dir / "widgets" / "skills" / "spin" / "SKILL.md"
    assert imported_skill.exists()


# ---------------------------------------------------------------------------
# 5. Import — all skills from a plugin
# ---------------------------------------------------------------------------

def test_plugins_import_all_from_plugin(cli_runner, tmp_path):
    """Import all skills from a plugin with 2 skills, verify both are imported."""
    runner, app = cli_runner

    source_dir = tmp_path / "source_cache"
    source_dir.mkdir()
    _create_fake_plugin(source_dir, org="acme", plugin="toolkit", skill_name="alpha")
    _create_fake_plugin(source_dir, org="acme", plugin="toolkit", skill_name="beta")

    dest_dir = tmp_path / "merkaba_plugins"
    dest_dir.mkdir()

    with patch("merkaba.cli.os.path.expanduser") as mock_expand:
        def _expand(path):
            if path == "~/.claude/plugins/cache":
                return str(source_dir)
            if path == "~/.merkaba/plugins":
                return str(dest_dir)
            from os.path import expanduser as real_expand
            return real_expand(path)

        mock_expand.side_effect = _expand
        result = runner.invoke(app, ["plugins", "import", "toolkit"])

    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output

    # Verify both skills were written
    assert (dest_dir / "toolkit" / "skills" / "alpha" / "SKILL.md").exists()
    assert (dest_dir / "toolkit" / "skills" / "beta" / "SKILL.md").exists()


# ---------------------------------------------------------------------------
# 6. Import — nonexistent plugin
# ---------------------------------------------------------------------------

def test_plugins_import_nonexistent(cli_runner, tmp_path):
    """Import a plugin that doesn't exist, verify error output."""
    runner, app = cli_runner

    source_dir = tmp_path / "empty_source"
    source_dir.mkdir()

    dest_dir = tmp_path / "merkaba_plugins"
    dest_dir.mkdir()

    with patch("merkaba.cli.os.path.expanduser") as mock_expand:
        def _expand(path):
            if path == "~/.claude/plugins/cache":
                return str(source_dir)
            if path == "~/.merkaba/plugins":
                return str(dest_dir)
            from os.path import expanduser as real_expand
            return real_expand(path)

        mock_expand.side_effect = _expand
        result = runner.invoke(app, ["plugins", "import", "ghost:phantom"])

    assert result.exit_code == 0  # CLI prints error but doesn't raise
    assert "not found" in result.output.lower() or "ghost" in result.output


# ---------------------------------------------------------------------------
# 7. Uninstall — not found
# ---------------------------------------------------------------------------

def test_plugins_uninstall_not_found(cli_runner, tmp_path):
    """Uninstall a nonexistent plugin, verify appropriate 'No files found' output."""
    runner, app = cli_runner

    empty_claude = tmp_path / "claude_home"
    empty_claude.mkdir()
    empty_merkaba = tmp_path / "merkaba_home_unsub"
    empty_merkaba.mkdir()

    with patch(
        "merkaba.plugins.uninstaller.PluginUninstaller.__init__",
        lambda self, **kwargs: (
            setattr(self, "claude_dir", str(empty_claude)),
            setattr(self, "merkaba_dir", str(empty_merkaba)),
            setattr(self, "settings_path", str(empty_claude / "settings.json")),
        ) and None,
    ):
        result = runner.invoke(app, ["plugins", "uninstall", "nonexistent", "--yes"])

    assert result.exit_code == 0
    assert "No files found" in result.output
