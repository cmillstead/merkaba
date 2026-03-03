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

    # ------------------------------------------------------------------
    # fire() tests
    # ------------------------------------------------------------------

    def test_hook_fire_matching_event(self):
        """fire() returns content for hooks whose trigger matches the event."""
        hook = Hook.from_markdown(
            "---\nname: on_msg\nevent: pre-message\n---\nBe helpful."
        )
        manager = HookManager(hooks=[hook])
        results = manager.fire("PRE_MESSAGE")
        assert results == ["Be helpful."]

    def test_hook_fire_no_match(self):
        """fire() returns an empty list when no hooks match the event."""
        hook = Hook.from_markdown(
            "---\nname: on_start\nevent: session-start\n---\nGreet user."
        )
        manager = HookManager(hooks=[hook])
        results = manager.fire("PRE_MESSAGE")
        assert results == []

    def test_hook_fire_template_substitution(self):
        """fire() replaces {{var}} placeholders with values from context."""
        hook = Hook.from_markdown(
            "---\nname: echo\nevent: pre-message\n---\nUser said: {{user_message}}"
        )
        manager = HookManager(hooks=[hook])
        results = manager.fire("PRE_MESSAGE", {"user_message": "hello world"})
        assert results == ["User said: hello world"]

    def test_hook_fire_error_swallowed(self):
        """fire() silently skips hooks that raise an exception during rendering."""
        # Craft a hook whose content triggers a rendering failure by patching
        # _render_template to raise for one specific hook, while a second hook
        # renders normally.  We achieve this by giving the broken hook a
        # pathological template that would cause _render_template to raise.
        # The simplest approach: replace the hook's content property with a
        # descriptor that raises — but since Hook is a dataclass we instead
        # monkeypatch _render_template at the module level for this one call.
        import merkaba.plugins.hooks as hooks_mod

        original_render = hooks_mod._render_template
        call_count = {"n": 0}

        def flaky_render(content, context):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated render failure")
            return original_render(content, context)

        hooks_mod._render_template = flaky_render
        try:
            hook_bad = Hook.from_markdown(
                "---\nname: bad\nevent: pre-message\n---\nThis will fail."
            )
            hook_good = Hook.from_markdown(
                "---\nname: good\nevent: pre-message\n---\nThis is fine."
            )
            manager = HookManager(hooks=[hook_bad, hook_good])
            results = manager.fire("PRE_MESSAGE")
            # The bad hook's error is swallowed; only the good hook's output remains.
            assert results == ["This is fine."]
        finally:
            hooks_mod._render_template = original_render
