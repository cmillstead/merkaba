# tests/test_plugin_agents.py
"""Tests for agent config loading."""

import os
import tempfile
import pytest

# Check if required dependencies are available
try:
    from merkaba.plugins.agents import AgentConfig, AgentManager
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    AgentConfig = None
    AgentManager = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_agent_from_markdown(self):
        """AgentConfig should parse from markdown with frontmatter."""
        content = """---
name: code-reviewer
model: deepseek-r1:70b
description: Code review specialist
---

You are a code reviewer. Focus on bugs and security.
"""
        agent = AgentConfig.from_markdown(content)
        assert agent.name == "code-reviewer"
        assert agent.model == "deepseek-r1:70b"
        assert agent.description == "Code review specialist"
        assert "security" in agent.system_prompt


class TestAgentManager:
    """Tests for AgentManager."""

    def test_load_agents_from_directory(self):
        """AgentManager should load agents from plugin directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = os.path.join(tmpdir, "test-plugin", "agents")
            os.makedirs(agents_dir)
            with open(os.path.join(agents_dir, "reviewer.md"), "w") as f:
                f.write("""---
name: reviewer
model: qwen3-coder:30b
description: Reviews code
---

Review carefully.
""")

            manager = AgentManager()
            manager.load_from_directory(tmpdir)

            assert "reviewer" in manager.list_agents()
            agent = manager.get("reviewer")
            assert agent.model == "qwen3-coder:30b"

    def test_get_returns_none_for_unknown(self):
        """get() should return None for unknown agent."""
        manager = AgentManager()
        assert manager.get("unknown") is None
