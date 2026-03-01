# src/merkaba/plugins/skills.py
"""Skill loading and management."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter


# Patterns that may indicate dangerous content in skills
# Note: These are regex patterns used to DETECT dangerous code, not execute it
DANGEROUS_SKILL_PATTERNS = [
    r"curl.*\|.*sh",      # curl pipe to shell
    r"wget.*\|.*sh",      # wget pipe to shell
    r"eval\s*\(",         # eval calls
    r"exec\s*\(",         # exec calls
    r"subprocess",        # subprocess module
    r"os\.system",        # os.system calls (pattern to detect, not usage)
    r"bash\s+-c",         # bash -c execution
    r"<script>",          # embedded scripts
    r"javascript:",       # javascript protocol
]


def scan_skill_content(content: str) -> list[str]:
    """Scan skill content for potentially dangerous patterns.

    This is a warning system to alert users about potentially dangerous
    skills, not a blocking mechanism.

    Args:
        content: The skill content to scan.

    Returns:
        List of warning strings for each matched pattern.
        Empty list if no patterns matched.
    """
    warnings = []

    for pattern in DANGEROUS_SKILL_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            warnings.append(f"Potentially dangerous pattern detected: {pattern}")

    return warnings


def _parse_manifest(post) -> "PluginManifest | None":
    """Parse PluginManifest from frontmatter if manifest fields are present."""
    from merkaba.plugins.sandbox import PluginManifest

    has_manifest = any(
        post.get(k) is not None
        for k in ("required_tools", "file_access", "permission_tier", "required_integrations")
    )
    if not has_manifest:
        return None
    return PluginManifest(
        name=post.get("name", "unnamed"),
        version=post.get("version", "0.1.0"),
        required_tools=post.get("required_tools", []),
        required_integrations=post.get("required_integrations", []),
        file_access=post.get("file_access", []),
        max_context_tokens=post.get("max_context_tokens", 4000),
        permission_tier=post.get("permission_tier", "MODERATE"),
    )


@dataclass
class Skill:
    """A skill loaded from a plugin."""

    name: str
    description: str
    content: str
    plugin_name: str = ""
    warnings: list[str] = field(default_factory=list)
    manifest: "PluginManifest | None" = None

    @classmethod
    def from_markdown(cls, markdown: str, plugin_name: str = "") -> "Skill":
        """Parse a skill from markdown with frontmatter."""
        post = frontmatter.loads(markdown)
        warnings = scan_skill_content(markdown)
        manifest = _parse_manifest(post)
        return cls(
            name=post.get("name", "unnamed"),
            description=post.get("description", ""),
            content=post.content,
            plugin_name=plugin_name,
            warnings=warnings,
            manifest=manifest,
        )

    @classmethod
    def from_file(cls, path: Path, plugin_name: str = "") -> "Skill":
        """Load a skill from a SKILL.md file."""
        with open(path) as f:
            return cls.from_markdown(f.read(), plugin_name)


@dataclass
class SkillManager:
    """Manages skill loading and retrieval."""

    skills: dict[str, Skill] = field(default_factory=dict)

    def load_from_directory(self, plugins_dir: str):
        """Load all skills from a plugins directory."""
        plugins_path = Path(plugins_dir)
        if not plugins_path.exists():
            return

        for plugin_dir in plugins_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            skills_dir = plugin_dir / "skills"
            if not skills_dir.exists():
                continue

            plugin_name = plugin_dir.name
            for skill_dir in skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill = Skill.from_file(skill_file, plugin_name)
                    self.skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self.skills.get(name)

    def list_skills(self) -> list[str]:
        """List all loaded skill names."""
        return list(self.skills.keys())

    def match(self, message: str) -> Skill | None:
        """Find a skill that matches the user message.

        Uses simple keyword matching on skill descriptions.
        Returns the first matching skill, or None.
        """
        message_lower = message.lower()

        # Keywords that suggest specific skills
        keyword_map = {
            "brainstorming": ["design", "feature", "create", "build", "implement", "new"],
            "test-driven-development": ["tdd", "test first", "write test"],
            "systematic-debugging": ["debug", "bug", "fix", "broken", "not working"],
            "writing-plans": ["plan", "implementation plan", "steps"],
        }

        for skill_name, keywords in keyword_map.items():
            if skill_name in self.skills:
                if any(kw in message_lower for kw in keywords):
                    return self.skills[skill_name]

        # Fallback: check skill descriptions
        for skill in self.skills.values():
            desc_words = skill.description.lower().split()
            if any(word in message_lower for word in desc_words if len(word) > 4):
                return skill

        return None
