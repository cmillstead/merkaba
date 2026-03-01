# src/merkaba/plugins/converter.py
"""Skill conversion strategies."""

import re
from dataclasses import dataclass
from datetime import datetime

import frontmatter


TOOL_MAP = {
    r'\bRead\b': 'file_read',
    r'\bWrite\b': 'file_write',
    r'\bEdit\b': 'file_write',
    r'\bGlob\b': 'file_list',
    r'\bGrep\b': 'file_list',
    r'\bTodoWrite\b': 'task_queue',
    r'\bBash\b': 'shell',
}

LLM_CONVERSION_PROMPT = """Rewrite this skill for Merkaba, a local AI agent with these tools:
- file_read: Read file contents
- file_write: Write to files
- file_list: List files in directory
- memory_search: Search agent memory
- shell: Execute shell commands

Remove or adapt references to unavailable tools (Bash, WebSearch, Task, TodoWrite).
Keep the core methodology intact. Output ONLY the converted markdown, no explanation.

Original skill:
{content}
"""


@dataclass
class SkillConverter:
    """Converts skill content to Merkaba-compatible format."""

    content: str
    model: str = "qwen3.5:122b"

    def apply_rule_based(self) -> str:
        """Apply rule-based tool name mapping."""
        result = self.content
        for pattern, replacement in TOOL_MAP.items():
            result = re.sub(pattern, replacement, result)
        return result

    def apply_llm_assisted(self) -> str:
        """Use LLM to rewrite skill for Merkaba compatibility."""
        from merkaba.agent import Agent  # Lazy import to avoid circular dependency

        agent = Agent(model=self.model)
        # Use replace instead of format to avoid issues with braces in content
        prompt = LLM_CONVERSION_PROMPT.replace("{content}", self.content)
        return agent.run(prompt)

    def add_metadata(
        self,
        imported_from: str,
        compatibility: int,
        conversion: str,
    ) -> str:
        """Add import metadata to skill frontmatter."""
        post = frontmatter.loads(self.content)

        post.metadata["imported_from"] = imported_from
        post.metadata["imported_at"] = datetime.now().isoformat()
        post.metadata["compatibility"] = compatibility
        post.metadata["conversion"] = conversion

        return frontmatter.dumps(post)
