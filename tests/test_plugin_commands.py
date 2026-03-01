# tests/test_plugin_commands.py
"""Tests for command loading."""

import os
import tempfile
import pytest

# Check if required dependencies are available
try:
    from merkaba.plugins.commands import Command, CommandManager
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    Command = None
    CommandManager = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestCommand:
    """Tests for Command dataclass."""

    def test_command_from_markdown(self):
        """Command should parse from markdown with frontmatter."""
        content = """---
name: commit
description: Create a git commit
---

# Commit Command

Generate a commit message and commit.
"""
        cmd = Command.from_markdown(content)
        assert cmd.name == "commit"
        assert cmd.description == "Create a git commit"
        assert "commit message" in cmd.content


class TestCommandManager:
    """Tests for CommandManager."""

    def test_load_commands_from_directory(self):
        """CommandManager should load commands from plugin directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock plugin structure
            cmd_dir = os.path.join(tmpdir, "test-plugin", "commands")
            os.makedirs(cmd_dir)
            with open(os.path.join(cmd_dir, "commit.md"), "w") as f:
                f.write("""---
name: commit
description: Create commit
---

Do the commit.
""")

            manager = CommandManager()
            manager.load_from_directory(tmpdir)

            assert "commit" in manager.list_commands()

    def test_get_returns_none_for_unknown(self):
        """get() should return None for unknown command."""
        manager = CommandManager()
        assert manager.get("unknown") is None
