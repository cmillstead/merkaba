# tests/test_agent_plugins.py
"""Tests for agent plugin integration."""

import pytest
from unittest.mock import MagicMock, patch

# Check if required dependencies are available
try:
    from merkaba.agent import Agent
    from merkaba.plugins import Skill
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    Agent = None
    Skill = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestAgentPluginIntegration:
    """Tests for Agent with plugin support."""

    @patch("merkaba.agent.ConversationLog")
    @patch("merkaba.agent.PluginRegistry")
    @patch("merkaba.agent.LLMClient")
    def test_agent_injects_skill_into_prompt(self, mock_llm, mock_registry, mock_memory):
        """Agent should inject active skill into system prompt."""
        # Setup mock skill
        mock_skill = Skill(
            name="test-skill",
            description="Test",
            content="Do the special thing.",
        )
        mock_registry_instance = MagicMock()
        mock_registry_instance.skills.get.return_value = mock_skill
        mock_registry.default.return_value = mock_registry_instance

        # Setup mock LLM response
        mock_llm_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = None
        mock_response.content = "Done"
        mock_llm_instance.chat_with_fallback.return_value = mock_response
        mock_llm.return_value = mock_llm_instance

        agent = Agent(plugins_enabled=True)
        agent.activate_skill("test-skill")
        agent.run("Hello")

        # Check that skill content was in the prompt
        call_args = mock_llm_instance.chat_with_fallback.call_args
        system_prompt = call_args.kwargs.get("system_prompt", "")
        assert "special thing" in system_prompt

    @patch("merkaba.agent.ConversationLog")
    @patch("merkaba.agent.PluginRegistry")
    @patch("merkaba.agent.LLMClient")
    def test_agent_works_without_plugins(self, mock_llm, mock_registry, mock_memory):
        """Agent should work when plugins_enabled=False."""
        mock_llm_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.tool_calls = None
        mock_response.content = "Hello!"
        mock_llm_instance.chat_with_fallback.return_value = mock_response
        mock_llm.return_value = mock_llm_instance

        agent = Agent(plugins_enabled=False)
        result = agent.run("Hi")

        assert result == "Hello!"
        mock_registry.default.assert_not_called()
