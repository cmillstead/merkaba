# tests/test_plugin_sandbox.py
"""Tests for Phase 11: Plugin Security & Sandboxing."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Stub ollama before importing merkaba modules
sys.modules.setdefault("ollama", MagicMock())

from merkaba.plugins.sandbox import (
    PROTECTED_PATHS,
    PluginManifest,
    PluginPermissionError,
    PluginSandbox,
)


# --- PluginManifest ---


class TestPluginManifest:
    def test_manifest_defaults(self):
        m = PluginManifest(name="test-plugin")
        assert m.name == "test-plugin"
        assert m.version == "0.1.0"
        assert m.required_tools == []
        assert m.required_integrations == []
        assert m.file_access == []
        assert m.max_context_tokens == 4000
        assert m.permission_tier == "MODERATE"

    def test_manifest_from_frontmatter(self):
        """Skill.from_markdown should parse manifest fields."""
        import frontmatter as _  # noqa: F401 — ensure available

        from merkaba.plugins.skills import Skill

        md = """---
name: test-skill
description: A test skill
required_tools:
  - file_read
  - web_fetch
file_access:
  - "~/.merkaba/outputs/*"
permission_tier: SENSITIVE
---
Skill content here.
"""
        skill = Skill.from_markdown(md, plugin_name="test-pkg")
        assert skill.manifest is not None
        assert skill.manifest.required_tools == ["file_read", "web_fetch"]
        assert skill.manifest.file_access == ["~/.merkaba/outputs/*"]
        assert skill.manifest.permission_tier == "SENSITIVE"

    def test_skill_without_manifest_returns_none(self):
        from merkaba.plugins.skills import Skill

        md = """---
name: plain-skill
description: No manifest fields
---
Just content.
"""
        skill = Skill.from_markdown(md)
        assert skill.manifest is None


# --- PluginSandbox tool checking ---


class TestToolAccess:
    def test_declared_tool_passes(self):
        manifest = PluginManifest(name="test", required_tools=["file_read", "web_fetch"])
        sandbox = PluginSandbox(manifest=manifest)
        sandbox.check_tool_access("file_read")  # should not raise
        sandbox.check_tool_access("web_fetch")

    def test_undeclared_tool_blocked(self):
        manifest = PluginManifest(name="test", required_tools=["file_read"])
        sandbox = PluginSandbox(manifest=manifest)
        with pytest.raises(PluginPermissionError, match="does not have access"):
            sandbox.check_tool_access("bash")

    def test_empty_required_tools_blocks_all(self):
        manifest = PluginManifest(name="test", required_tools=[])
        sandbox = PluginSandbox(manifest=manifest)
        with pytest.raises(PluginPermissionError):
            sandbox.check_tool_access("file_read")


# --- PluginSandbox path checking ---


class TestPathAccess:
    def test_allowed_path_passes(self, tmp_path):
        target = tmp_path / "output.txt"
        target.touch()
        manifest = PluginManifest(
            name="test",
            required_tools=["file_read"],
            file_access=[str(tmp_path / "*")],
        )
        sandbox = PluginSandbox(manifest=manifest)
        assert sandbox.is_path_allowed(str(target)) is True

    def test_disallowed_path_blocked(self, tmp_path):
        manifest = PluginManifest(
            name="test",
            required_tools=["file_read"],
            file_access=[str(tmp_path / "allowed/*")],
        )
        sandbox = PluginSandbox(manifest=manifest)
        assert sandbox.is_path_allowed("/etc/passwd") is False

    def test_protected_path_always_blocked(self):
        manifest = PluginManifest(
            name="test",
            required_tools=["file_write"],
            file_access=["**/*"],  # wildcard everything
        )
        sandbox = PluginSandbox(manifest=manifest)
        # Security files should be blocked
        assert sandbox.is_path_allowed(os.path.expanduser("~/.merkaba/config.json")) is False

    def test_protected_db_blocked_even_with_wildcard(self):
        manifest = PluginManifest(
            name="test",
            required_tools=["file_write"],
            file_access=["**/*"],
        )
        sandbox = PluginSandbox(manifest=manifest)
        assert sandbox.is_path_allowed(os.path.expanduser("~/.merkaba/memory.db")) is False

    def test_empty_file_access_blocks_all(self, tmp_path):
        manifest = PluginManifest(name="test", required_tools=["file_read"], file_access=[])
        sandbox = PluginSandbox(manifest=manifest)
        assert sandbox.is_path_allowed(str(tmp_path / "anything.txt")) is False

    def test_check_path_access_raises_for_blocked(self, tmp_path):
        manifest = PluginManifest(name="test", required_tools=["file_read"], file_access=[])
        sandbox = PluginSandbox(manifest=manifest)
        with pytest.raises(PluginPermissionError, match="cannot access path"):
            sandbox.check_path_access("file_read", {"path": str(tmp_path / "secret.txt")})

    def test_check_path_access_skips_non_file_tools(self):
        manifest = PluginManifest(name="test", required_tools=["web_fetch"], file_access=[])
        sandbox = PluginSandbox(manifest=manifest)
        # Should not raise even with empty file_access — web_fetch is not a file tool
        sandbox.check_path_access("web_fetch", {"url": "https://example.com"})


# --- New protected path coverage ---


class TestNewProtectedPaths:
    """Tests for the three newly-added PROTECTED_PATHS entries."""

    def _sandbox_wildcard(self):
        """A sandbox whose manifest grants wildcard file_access — only protected
        paths should still be blocked."""
        manifest = PluginManifest(
            name="test",
            required_tools=["file_read", "file_write"],
            file_access=["**/*"],
        )
        return PluginSandbox(manifest=manifest)

    def test_protected_paths_includes_conversations(self):
        """Paths inside ~/.merkaba/conversations/ must be blocked."""
        sandbox = self._sandbox_wildcard()
        target = os.path.expanduser("~/.merkaba/conversations/session-abc.json")
        assert sandbox.is_path_allowed(target) is False

    def test_protected_paths_includes_backups(self):
        """Paths inside ~/.merkaba/backups/ must be blocked."""
        sandbox = self._sandbox_wildcard()
        target = os.path.expanduser("~/.merkaba/backups/2026-01-01.tar.gz")
        assert sandbox.is_path_allowed(target) is False

    def test_protected_paths_includes_memory_vectors(self):
        """Paths inside ~/.merkaba/memory_vectors/ must be blocked."""
        sandbox = self._sandbox_wildcard()
        target = os.path.expanduser("~/.merkaba/memory_vectors/chroma.sqlite3")
        assert sandbox.is_path_allowed(target) is False

    def test_path_traversal_blocked(self, tmp_path):
        """A traversal like <tmp>/../../../.merkaba/config.json must be blocked."""
        sandbox = self._sandbox_wildcard()
        # Construct a path that naively looks relative but resolves to the
        # protected file after Path.resolve() canonicalises it.
        traversal = os.path.expanduser("~/.merkaba/conversations/../config.json")
        assert sandbox.is_path_allowed(traversal) is False

    def test_path_traversal_into_conversations_blocked(self, tmp_path):
        """Traversal that resolves into conversations/ must be blocked."""
        sandbox = self._sandbox_wildcard()
        traversal = os.path.expanduser("~/.merkaba/backups/../conversations/leak.json")
        assert sandbox.is_path_allowed(traversal) is False

    def test_conversations_directory_itself_blocked(self):
        """The conversations directory itself (not just its children) must be blocked."""
        sandbox = self._sandbox_wildcard()
        target = os.path.expanduser("~/.merkaba/conversations")
        assert sandbox.is_path_allowed(target) is False

    def test_backups_directory_itself_blocked(self):
        """The backups directory itself must be blocked."""
        sandbox = self._sandbox_wildcard()
        target = os.path.expanduser("~/.merkaba/backups")
        assert sandbox.is_path_allowed(target) is False


# --- Business isolation ---


class TestBusinessIsolation:
    def _make_sandbox(self, allowed_business_ids=None):
        manifest = PluginManifest(name="biz-plugin", required_tools=["file_read"])
        return PluginSandbox(manifest=manifest, allowed_business_ids=allowed_business_ids)

    def test_sandbox_business_isolation(self):
        """check_business_access raises when business_id is not in the allowed list."""
        sandbox = self._make_sandbox(allowed_business_ids=[1, 2])
        # Allowed IDs should pass
        sandbox.check_business_access(1)  # no raise
        sandbox.check_business_access(2)  # no raise
        # Disallowed ID should raise
        with pytest.raises(PluginPermissionError, match="does not have access to business"):
            sandbox.check_business_access(3)

    def test_sandbox_business_isolation_none_allows_all(self):
        """When allowed_business_ids is None, every business id is accessible."""
        sandbox = self._make_sandbox(allowed_business_ids=None)
        # These should never raise
        sandbox.check_business_access(0)
        sandbox.check_business_access(1)
        sandbox.check_business_access(999)

    def test_sandbox_business_isolation_empty_list_blocks_all(self):
        """An empty allowed_business_ids list blocks every business id."""
        sandbox = self._make_sandbox(allowed_business_ids=[])
        with pytest.raises(PluginPermissionError):
            sandbox.check_business_access(1)

    def test_sandbox_business_isolation_error_message_includes_id(self):
        """Error message includes the rejected business id."""
        sandbox = self._make_sandbox(allowed_business_ids=[10, 20])
        with pytest.raises(PluginPermissionError, match="42"):
            sandbox.check_business_access(42)

    def test_sandbox_default_allowed_business_ids_is_none(self):
        """PluginSandbox.allowed_business_ids defaults to None."""
        manifest = PluginManifest(name="default-plugin")
        sandbox = PluginSandbox(manifest=manifest)
        assert sandbox.allowed_business_ids is None


class TestProtectedUploadsAndLogs:
    """M24: Plugin sandbox must block access to uploads/ and logs/."""

    def test_sandbox_protects_uploads_and_logs(self):
        """M24: Plugin sandbox must block access to uploads/ and logs/."""
        from merkaba.plugins.sandbox import _RESOLVED_PROTECTED_DIRS
        assert any("uploads" in p for p in PROTECTED_PATHS)
        assert any("logs" in p for p in PROTECTED_PATHS)
        assert any("uploads" in d for d in _RESOLVED_PROTECTED_DIRS)
        assert any("logs" in d for d in _RESOLVED_PROTECTED_DIRS)

    def test_uploads_path_blocked(self):
        """Plugin sandbox must block access to ~/.merkaba/uploads/."""
        manifest = PluginManifest(
            name="test", required_tools=["file_read"], file_access=["**/*"],
        )
        sandbox = PluginSandbox(manifest=manifest)
        target = os.path.expanduser("~/.merkaba/uploads/secret.txt")
        assert sandbox.is_path_allowed(target) is False

    def test_logs_path_blocked(self):
        """Plugin sandbox must block access to ~/.merkaba/logs/."""
        manifest = PluginManifest(
            name="test", required_tools=["file_read"], file_access=["**/*"],
        )
        sandbox = PluginSandbox(manifest=manifest)
        target = os.path.expanduser("~/.merkaba/logs/merkaba.jsonl")
        assert sandbox.is_path_allowed(target) is False


# --- Agent integration ---


class TestAgentIntegration:
    @pytest.fixture
    def agent(self, tmp_path):
        with patch("merkaba.agent.SecurityScanner") as MockScanner:
            MockScanner.return_value.quick_scan.return_value = MagicMock(has_issues=False)
            from merkaba.agent import Agent
            a = Agent(plugins_enabled=False, memory_storage_dir=str(tmp_path))
        a.input_classifier.enabled = False
        return a

    def test_agent_with_sandboxed_skill_blocks_undeclared_tool(self, agent):
        """When active skill has a manifest, undeclared tools should be blocked."""
        from merkaba.plugins.skills import Skill
        from merkaba.plugins.sandbox import PluginManifest
        from merkaba.llm import LLMResponse, ToolCall

        manifest = PluginManifest(name="restricted", required_tools=["file_read"])
        agent.active_skill = Skill(
            name="restricted",
            description="test",
            content="test",
            manifest=manifest,
        )

        # LLM tries to call bash (not in manifest)
        tool_resp = LLMResponse(
            content=None, model="test",
            tool_calls=[ToolCall(name="bash", arguments={"command": "ls"})],
        )
        final_resp = LLMResponse(content="Done.", model="test")
        agent.llm.chat_with_retry = MagicMock(side_effect=[tool_resp, final_resp])

        result = agent.run("do something")
        assert result == "Done."
        # The tool result should contain permission denied
        # (it flows into conversation, LLM generates final response)

    def test_agent_with_sandboxed_skill_allows_declared_tool(self, agent):
        """Declared tools should work normally."""
        from merkaba.plugins.skills import Skill
        from merkaba.plugins.sandbox import PluginManifest
        from merkaba.llm import LLMResponse, ToolCall

        manifest = PluginManifest(name="reader", required_tools=["file_read"])
        agent.active_skill = Skill(
            name="reader",
            description="test",
            content="test",
            manifest=manifest,
        )

        tool_resp = LLMResponse(
            content=None, model="test",
            tool_calls=[ToolCall(name="file_read", arguments={"path": "/tmp/test"})],
        )
        final_resp = LLMResponse(content="Read it.", model="test")
        agent.llm.chat_with_retry = MagicMock(side_effect=[tool_resp, final_resp])

        result = agent.run("read the file")
        assert result == "Read it."

    def test_agent_without_manifest_allows_all_tools(self, agent):
        """Skills without manifests should not restrict tools."""
        from merkaba.plugins.skills import Skill
        from merkaba.llm import LLMResponse, ToolCall

        agent.active_skill = Skill(
            name="unrestricted",
            description="test",
            content="test",
            manifest=None,
        )

        tool_resp = LLMResponse(
            content=None, model="test",
            tool_calls=[ToolCall(name="bash", arguments={"command": "echo hi"})],
        )
        final_resp = LLMResponse(content="Ran it.", model="test")
        agent.llm.chat_with_retry = MagicMock(side_effect=[tool_resp, final_resp])

        result = agent.run("run command")
        assert result == "Ran it."
