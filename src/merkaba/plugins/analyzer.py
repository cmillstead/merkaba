# src/merkaba/plugins/analyzer.py
"""Skill compatibility analysis."""

import re
from dataclasses import dataclass, field
from enum import Enum


class ConversionStrategy(Enum):
    """Strategy for converting a skill."""
    RULE_BASED = "rule_based"
    LLM_ASSISTED = "llm_assisted"
    SKIP = "skip"


# Claude Code tools to detect
CLAUDE_TOOLS = {
    "Read", "Write", "Edit", "Glob", "Grep", "Bash",
    "WebSearch", "WebFetch", "Task", "TodoWrite",
    "AskUserQuestion", "EnterPlanMode", "Skill",
}

# Tool compatibility weights (100 = full support, 0 = not available)
TOOL_WEIGHTS = {
    "Read": 100,
    "Write": 100,
    "Edit": 100,
    "Glob": 100,       # Now fully supported
    "Grep": 100,       # Now fully supported
    "Bash": 100,       # Now fully supported
    "WebSearch": 0,
    "WebFetch": 100,   # Now fully supported
    "Task": 0,
    "TodoWrite": 50,
    "AskUserQuestion": 50,
    "EnterPlanMode": 50,
    "Skill": 50,
}


@dataclass
class SkillAnalyzer:
    """Analyzes skill content for compatibility."""

    content: str
    detected_tools: set[str] = field(default_factory=set)
    compatibility_score: int = field(init=False, default=100)
    strategy: ConversionStrategy = field(init=False)
    missing_tools: set[str] = field(init=False, default_factory=set)

    def __post_init__(self):
        self._detect_tools()
        self._calculate_score()
        self._determine_strategy()

    def _detect_tools(self):
        """Detect Claude Code tool references in content."""
        for tool in CLAUDE_TOOLS:
            # Match tool name as word boundary (not part of another word)
            pattern = rf'\b{tool}\b'
            if re.search(pattern, self.content, re.IGNORECASE):
                self.detected_tools.add(tool)

        # Also detect ```bash code blocks
        if re.search(r'```bash', self.content, re.IGNORECASE):
            self.detected_tools.add("Bash")

    def _calculate_score(self) -> None:
        """Calculate compatibility score based on detected tools."""
        if not self.detected_tools:
            self.compatibility_score = 100
            return

        total_weight = sum(
            TOOL_WEIGHTS.get(tool, 0) for tool in self.detected_tools
        )
        self.compatibility_score = total_weight // len(self.detected_tools)

    def _determine_strategy(self) -> None:
        """Determine conversion strategy based on score."""
        # Find tools with no Merkaba equivalent
        self.missing_tools = {
            tool for tool in self.detected_tools
            if TOOL_WEIGHTS.get(tool, 0) == 0
        }

        if self.compatibility_score >= 90:
            self.strategy = ConversionStrategy.RULE_BASED
        elif self.compatibility_score >= 50:
            self.strategy = ConversionStrategy.LLM_ASSISTED
        else:
            self.strategy = ConversionStrategy.SKIP
