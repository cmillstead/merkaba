# src/merkaba/plugins/hooks.py
"""Hook loading and management."""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)


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
                try:
                    hook = Hook.from_file(hook_file, plugin_name)
                    self.hooks.append(hook)
                except Exception as e:
                    logger.warning("Failed to load hook %s: %s", hook_file, e)

    def get_hooks_for_event(self, event: HookEvent) -> list[Hook]:
        """Get all hooks subscribed to an event."""
        return [h for h in self.hooks if h.event == event]

    def fire(self, event: str, context: dict | None = None) -> list[str]:
        """Fire all hooks matching the given event and return rendered content.

        Args:
            event: Event name string (e.g. "SESSION_START", "PRE_MESSAGE").
                   Accepts both enum value strings ("session-start") and
                   uppercase constant names ("SESSION_START").
            context: Optional dict used for ``{{var}}`` template substitution
                     in hook content.

        Returns:
            List of rendered content strings from all matching hooks.
            Hooks that raise exceptions are silently skipped.
        """
        if context is None:
            context = {}

        # Normalise the event string — accept "SESSION_START" or "session-start"
        normalised = event.lower().replace("_", "-")

        results: list[str] = []
        for hook in self.hooks:
            if hook.event.value != normalised:
                continue
            try:
                rendered = _render_template(hook.content, context)
                results.append(rendered)
            except Exception as e:
                logger.warning(
                    "Hook '%s' (plugin=%s) raised an error on event '%s': %s",
                    hook.name, hook.plugin_name, event, e,
                )
        return results


def _render_template(content: str, context: dict) -> str:
    """Replace ``{{key}}`` placeholders in *content* with values from *context*.

    Unresolved placeholders are left unchanged so callers can always inspect
    the raw template variable name.
    """
    import re

    def replacer(match: re.Match) -> str:
        key = match.group(1).strip()
        # Support simple dot-path lookup (e.g. ``{{tool.name}}``)
        value = context
        for part in key.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
            if value is None:
                break
        if value is None:
            return match.group(0)  # leave placeholder intact
        return str(value)

    return re.sub(r"\{\{(.+?)\}\}", replacer, content)
