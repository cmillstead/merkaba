# src/merkaba/plugins/hooks.py
"""Hook loading and management."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import frontmatter


class HookEvent(Enum):
    """Events that hooks can subscribe to."""

    SESSION_START = "session-start"
    PRE_MESSAGE = "pre-message"
    POST_MESSAGE = "post-message"
    PRE_TOOL = "pre-tool"
    POST_TOOL = "post-tool"
    FILE_CHANGED = "file-changed"


@dataclass
class Hook:
    """A hook loaded from a plugin."""

    name: str
    event: HookEvent
    content: str
    plugin_name: str = ""

    @classmethod
    def from_markdown(cls, markdown: str, plugin_name: str = "") -> "Hook":
        """Parse a hook from markdown with frontmatter."""
        post = frontmatter.loads(markdown)
        event_str = post.get("event", "session-start")
        try:
            event = HookEvent(event_str)
        except ValueError:
            event = HookEvent.SESSION_START
        return cls(
            name=post.get("name", "unnamed"),
            event=event,
            content=post.content,
            plugin_name=plugin_name,
        )

    @classmethod
    def from_file(cls, path: Path, plugin_name: str = "") -> "Hook":
        """Load a hook from a markdown file."""
        with open(path) as f:
            return cls.from_markdown(f.read(), plugin_name)


@dataclass
class HookManager:
    """Manages hook loading and event subscription."""

    hooks: list[Hook] = field(default_factory=list)

    def load_from_directory(self, plugins_dir: str):
        """Load all hooks from a plugins directory."""
        plugins_path = Path(plugins_dir)
        if not plugins_path.exists():
            return

        for plugin_dir in plugins_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            hooks_dir = plugin_dir / "hooks"
            if not hooks_dir.exists():
                continue

            plugin_name = plugin_dir.name
            for hook_file in hooks_dir.glob("*.md"):
                hook = Hook.from_file(hook_file, plugin_name)
                self.hooks.append(hook)

    def get_hooks_for_event(self, event: HookEvent) -> list[Hook]:
        """Get all hooks subscribed to an event."""
        return [h for h in self.hooks if h.event == event]
