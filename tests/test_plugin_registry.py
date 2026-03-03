# tests/test_plugin_registry.py
"""Tests for PluginRegistry."""

import os
import tempfile
import pytest

# Check if required dependencies are available
try:
    from merkaba.plugins.registry import PluginRegistry
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    PluginRegistry = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def test_registry_loads_all_components(self):
        """PluginRegistry should load skills, commands, hooks, agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock plugin with all components
            plugin_dir = os.path.join(tmpdir, "test-plugin")

            # Skill
            skill_dir = os.path.join(plugin_dir, "skills", "my-skill")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: my-skill\ndescription: test\n---\nContent")

            # Command
            cmd_dir = os.path.join(plugin_dir, "commands")
            os.makedirs(cmd_dir)
            with open(os.path.join(cmd_dir, "my-cmd.md"), "w") as f:
                f.write("---\nname: my-cmd\ndescription: test\n---\nContent")

            # Hook
            hook_dir = os.path.join(plugin_dir, "hooks")
            os.makedirs(hook_dir)
            with open(os.path.join(hook_dir, "my-hook.md"), "w") as f:
                f.write("---\nname: my-hook\nevent: session-start\n---\nContent")

            # Agent
            agent_dir = os.path.join(plugin_dir, "agents")
            os.makedirs(agent_dir)
            with open(os.path.join(agent_dir, "my-agent.md"), "w") as f:
                f.write("---\nname: my-agent\nmodel: test\n---\nContent")

            registry = PluginRegistry()
            registry.load_plugins([tmpdir])

            assert "my-skill" in registry.skills.list_skills()
            assert "my-cmd" in registry.commands.list_commands()
            assert "my-agent" in registry.agents.list_agents()
            assert len(registry.hooks.hooks) == 1

    def test_registry_loads_from_multiple_dirs(self):
        """PluginRegistry should load from multiple directories."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                # Plugin in dir1
                skill_dir1 = os.path.join(tmpdir1, "plugin1", "skills", "skill1")
                os.makedirs(skill_dir1)
                with open(os.path.join(skill_dir1, "SKILL.md"), "w") as f:
                    f.write("---\nname: skill1\ndescription: test\n---\n")

                # Plugin in dir2
                skill_dir2 = os.path.join(tmpdir2, "plugin2", "skills", "skill2")
                os.makedirs(skill_dir2)
                with open(os.path.join(skill_dir2, "SKILL.md"), "w") as f:
                    f.write("---\nname: skill2\ndescription: test\n---\n")

                registry = PluginRegistry()
                registry.load_plugins([tmpdir1, tmpdir2])

                skills = registry.skills.list_skills()
                assert "skill1" in skills
                assert "skill2" in skills


class TestDefaultLoadPaths:
    """Tests for PluginRegistry.default() load path safety."""

    def test_default_does_not_load_claude_plugin_cache(self):
        """PluginRegistry.default() must not include ~/.claude/plugins/cache.

        Loading from the Claude Code plugin cache directory is a cross-contamination
        risk: any Claude Code plugin installed there would be auto-loaded as a
        Merkaba plugin and could execute hooks on every agent message.
        """
        import unittest.mock as mock

        loaded_dirs: list[str] = []

        def capture_load(dirs: list[str]) -> None:
            loaded_dirs.extend(dirs)

        registry = PluginRegistry()
        with mock.patch.object(registry, "load_plugins", side_effect=capture_load):
            with mock.patch.object(registry, "load_skill_context"):
                with mock.patch.object(PluginRegistry, "__new__", return_value=registry):
                    PluginRegistry.default()

        for d in loaded_dirs:
            assert ".claude" not in d, (
                f"Plugin load path '{d}' references the Claude Code directory — "
                "this is a cross-contamination risk and must be removed."
            )
            assert "claude/plugins/cache" not in d, (
                f"Plugin load path '{d}' is the Claude Code plugin cache — "
                "this path must not appear in plugin load directories."
            )

    def test_default_includes_merkaba_plugins_dir(self):
        """PluginRegistry.default() must always include ~/.merkaba/plugins."""
        import unittest.mock as mock

        loaded_dirs: list[str] = []

        def capture_load(dirs: list[str]) -> None:
            loaded_dirs.extend(dirs)

        registry = PluginRegistry()
        with mock.patch.object(registry, "load_plugins", side_effect=capture_load):
            with mock.patch.object(registry, "load_skill_context"):
                with mock.patch.object(PluginRegistry, "__new__", return_value=registry):
                    PluginRegistry.default()

        assert any("merkaba/plugins" in d for d in loaded_dirs), (
            "PluginRegistry.default() must include ~/.merkaba/plugins in load paths; "
            f"got: {loaded_dirs}"
        )


class TestSkillContext:
    """Tests for global skill context loading."""

    def test_registry_loads_skill_context(self):
        """PluginRegistry should load ~/.merkaba/skill-context.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context_file = os.path.join(tmpdir, "skill-context.md")
            with open(context_file, "w") as f:
                f.write("# Merkaba Context\n\nBe helpful and concise.")

            registry = PluginRegistry()
            registry.load_skill_context(context_file)

            assert "helpful" in registry.skill_context
            assert "concise" in registry.skill_context

    def test_registry_returns_empty_if_no_context_file(self):
        """skill_context should be empty if file doesn't exist."""
        registry = PluginRegistry()
        registry.load_skill_context("/nonexistent/path.md")

        assert registry.skill_context == ""
