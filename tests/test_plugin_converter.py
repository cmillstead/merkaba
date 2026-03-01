# tests/test_plugin_converter.py
import pytest
from unittest.mock import Mock, patch

# Check if required dependencies are available
try:
    from merkaba.plugins.converter import SkillConverter
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    SkillConverter = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestRuleBasedConversion:
    def test_maps_read_to_file_read(self):
        content = "Use the Read tool to examine files."
        converter = SkillConverter(content)
        result = converter.apply_rule_based()
        assert "file_read" in result
        assert "Read tool" not in result

    def test_maps_write_to_file_write(self):
        content = "Use Write to save the file."
        converter = SkillConverter(content)
        result = converter.apply_rule_based()
        assert "file_write" in result

    def test_preserves_non_tool_content(self):
        content = "# My Skill\n\nThis is methodology."
        converter = SkillConverter(content)
        result = converter.apply_rule_based()
        assert "# My Skill" in result
        assert "This is methodology." in result


class TestLLMConversion:
    def test_calls_llm_with_prompt(self):
        content = "Use TodoWrite to track progress."
        converter = SkillConverter(content)

        mock_agent = Mock()
        mock_agent.run.return_value = "Use a checklist to track progress."

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            result = converter.apply_llm_assisted()

        mock_agent.run.assert_called_once()
        call_arg = mock_agent.run.call_args[0][0]
        assert "TodoWrite" in call_arg  # Original content in prompt
        assert "file_read" in call_arg  # Available tools mentioned

    def test_returns_converted_content(self):
        content = "Use TodoWrite."
        converter = SkillConverter(content)

        mock_agent = Mock()
        mock_agent.run.return_value = "Track your progress manually."

        with patch("merkaba.agent.Agent", return_value=mock_agent):
            result = converter.apply_llm_assisted()

        assert result == "Track your progress manually."


class TestMetadataHeader:
    def test_adds_import_metadata(self):
        content = """---
name: my-skill
description: A test skill
---
# Content
"""
        converter = SkillConverter(content)
        result = converter.add_metadata(
            imported_from="superpowers",
            compatibility=85,
            conversion="rule_based",
        )

        assert "imported_from: superpowers" in result
        assert "compatibility: 85" in result
        assert "conversion: rule_based" in result
        assert "imported_at:" in result
