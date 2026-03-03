# src/merkaba/plugins/commands.py
"""Command loading and management."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)


@dataclass
class Command:
    """A command loaded from a plugin."""

    name: str
    description: str
    content: str
    plugin_name: str = ""

    @classmethod
    def from_markdown(cls, markdown: str, plugin_name: str = "") -> "Command":
        """Parse a command from markdown with frontmatter."""
        post = frontmatter.loads(markdown)
        return cls(
            name=post.get("name", "unnamed"),
            description=post.get("description", ""),
            content=post.content,
            plugin_name=plugin_name,
        )

    @classmethod
    def from_file(cls, path: Path, plugin_name: str = "") -> "Command":
        """Load a command from a markdown file."""
        with open(path) as f:
            return cls.from_markdown(f.read(), plugin_name)


@dataclass
class CommandManager:
    """Manages command loading and retrieval."""

    commands: dict[str, Command] = field(default_factory=dict)

    def load_from_directory(self, plugins_dir: str):
        """Load all commands from a plugins directory."""
        plugins_path = Path(plugins_dir)
        if not plugins_path.exists():
            return

        for plugin_dir in plugins_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            commands_dir = plugin_dir / "commands"
            if not commands_dir.exists():
                continue

            plugin_name = plugin_dir.name
            for cmd_file in commands_dir.glob("*.md"):
                try:
                    cmd = Command.from_file(cmd_file, plugin_name)
                    self.commands[cmd.name] = cmd
                except Exception as e:
                    logger.warning("Failed to load command %s: %s", cmd_file, e)

    def get(self, name: str) -> Command | None:
        """Get a command by name."""
        return self.commands.get(name)

    def list_commands(self) -> list[str]:
        """List all loaded command names."""
        return list(self.commands.keys())
