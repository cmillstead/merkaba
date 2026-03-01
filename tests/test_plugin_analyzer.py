# tests/test_plugin_analyzer.py
"""Tests for skill compatibility analysis."""

import pytest

# Check if required dependencies are available
try:
    from merkaba.plugins.analyzer import ConversionStrategy, SkillAnalyzer
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    ConversionStrategy = None
    SkillAnalyzer = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


class TestToolDetection:
    """Tests for detecting Claude Code tool references."""

    def test_detects_bash_tool(self):
        """Should detect Bash tool from code block."""
        content = """
# My Skill

Run this command:
```bash
pytest tests/
```
"""
        analyzer = SkillAnalyzer(content)
        assert "Bash" in analyzer.detected_tools

    def test_detects_read_tool(self):
        """Should detect Read tool from text reference."""
        content = "Use the Read tool to examine the file."
        analyzer = SkillAnalyzer(content)
        assert "Read" in analyzer.detected_tools

    def test_detects_multiple_tools(self):
        """Should detect all referenced tools."""
        content = """
Use Read to check the file.
Then use Write to save changes.
Run Bash commands as needed.
"""
        analyzer = SkillAnalyzer(content)
        assert analyzer.detected_tools == {"Read", "Write", "Bash"}

    def test_no_tools_detected(self):
        """Should return empty set when no tools referenced."""
        content = "This is a pure methodology guide with no tool references."
        analyzer = SkillAnalyzer(content)
        assert analyzer.detected_tools == set()

    def test_detects_case_insensitive(self):
        """Should detect tools regardless of case."""
        content = "Use the read tool and the WRITE tool."
        analyzer = SkillAnalyzer(content)
        assert "Read" in analyzer.detected_tools
        assert "Write" in analyzer.detected_tools

    def test_does_not_match_partial_words(self):
        """Should not match tool names within other words."""
        content = "The readable file was written by the author."
        analyzer = SkillAnalyzer(content)
        assert "Read" not in analyzer.detected_tools
        assert "Write" not in analyzer.detected_tools


class TestCompatibilityScoring:
    def test_pure_methodology_skill_scores_100(self):
        content = "This is just instructions, no tools."
        analyzer = SkillAnalyzer(content)
        assert analyzer.compatibility_score == 100

    def test_read_write_scores_100(self):
        content = "Use Read and Write tools."
        analyzer = SkillAnalyzer(content)
        assert analyzer.compatibility_score == 100

    def test_bash_only_scores_100(self):
        """Bash is now fully supported."""
        content = "Run Bash commands to deploy."
        analyzer = SkillAnalyzer(content)
        assert analyzer.compatibility_score == 100

    def test_mixed_tools_scores_partial(self):
        content = "Use Read to check, then Task to dispatch."
        analyzer = SkillAnalyzer(content)
        # Read=100%, Task=0%, average=50%
        assert analyzer.compatibility_score == 50

    def test_todowrite_scores_50(self):
        content = "Use TodoWrite to track progress."
        analyzer = SkillAnalyzer(content)
        assert analyzer.compatibility_score == 50


class TestConversionStrategy:
    def test_high_score_uses_rule_based(self):
        content = "Use Read and Write tools."
        analyzer = SkillAnalyzer(content)
        assert analyzer.strategy == ConversionStrategy.RULE_BASED

    def test_medium_score_uses_llm(self):
        content = "Use TodoWrite to track."
        analyzer = SkillAnalyzer(content)
        assert analyzer.strategy == ConversionStrategy.LLM_ASSISTED

    def test_low_score_skips(self):
        content = "Use Task and WebSearch."
        analyzer = SkillAnalyzer(content)
        # Task=0%, WebSearch=0%, average=0%
        assert analyzer.strategy == ConversionStrategy.SKIP

    def test_missing_tools_list(self):
        content = "Use Task and WebSearch."
        analyzer = SkillAnalyzer(content)
        assert analyzer.missing_tools == {"Task", "WebSearch"}
