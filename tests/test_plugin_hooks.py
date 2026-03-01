# tests/test_plugin_hooks.py
"""Tests for hook loading."""

import os
import tempfile
import pytest

# Check if required dependencies are available
try:
    from merkaba.plugins.hooks import Hook, HookManager, HookEvent
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    Hook = None
    HookManager = None
    HookEvent = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestHook:
    """Tests for Hook dataclass."""

    def test_hook_from_markdown(self):
        """Hook should parse from markdown with frontmatter."""
        content = """---
name: greeting
event: session-start
---

Greet the user warmly.
"""
        hook = Hook.from_markdown(content)
        assert hook.name == "greeting"
        assert hook.event == HookEvent.SESSION_START
        assert "Greet" in hook.content


class TestHookManager:
    """Tests for HookManager."""

    def test_load_hooks_from_directory(self):
        """HookManager should load hooks from plugin directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hook_dir = os.path.join(tmpdir, "test-plugin", "hooks")
            os.makedirs(hook_dir)
            with open(os.path.join(hook_dir, "greeting.md"), "w") as f:
                f.write("""---
name: greeting
event: session-start
---

Say hello.
""")

            manager = HookManager()
            manager.load_from_directory(tmpdir)

            hooks = manager.get_hooks_for_event(HookEvent.SESSION_START)
            assert len(hooks) == 1
            assert hooks[0].name == "greeting"

    def test_get_hooks_returns_empty_for_no_matches(self):
        """get_hooks_for_event() should return empty list if no matches."""
        manager = HookManager()
        assert manager.get_hooks_for_event(HookEvent.PRE_MESSAGE) == []
