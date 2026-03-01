# src/merkaba/plugins/registry.py
"""Central plugin registry."""

import os
from dataclasses import dataclass, field

from merkaba.plugins.skills import SkillManager
from merkaba.plugins.commands import CommandManager
from merkaba.plugins.hooks import HookManager
from merkaba.plugins.agents import AgentManager


@dataclass
class PluginRegistry:
    """Central registry for all plugin components."""

    skills: SkillManager = field(default_factory=SkillManager)
    commands: CommandManager = field(default_factory=CommandManager)
    hooks: HookManager = field(default_factory=HookManager)
    agents: AgentManager = field(default_factory=AgentManager)
    skill_context: str = ""

    def load_skill_context(self, path: str):
        """Load global skill context from file."""
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            with open(expanded) as f:
                self.skill_context = f.read()
        else:
            self.skill_context = ""

    def load_plugins(self, plugin_dirs: list[str]):
        """Load all plugins from the given directories."""
        for plugin_dir in plugin_dirs:
            expanded = os.path.expanduser(plugin_dir)
            if not os.path.exists(expanded):
                continue

            self.skills.load_from_directory(expanded)
            self.commands.load_from_directory(expanded)
            self.hooks.load_from_directory(expanded)
            self.agents.load_from_directory(expanded)

    @classmethod
    def default(cls) -> "PluginRegistry":
        """Create registry with default plugin directories."""
        registry = cls()
        registry.load_plugins([
            "~/.claude/plugins/cache",
            "~/.merkaba/plugins",
        ])
        registry.load_skill_context("~/.merkaba/skill-context.md")
        return registry
