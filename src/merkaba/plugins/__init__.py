# src/friday/plugins/__init__.py
"""Plugin system for Friday."""

from friday.plugins.skills import Skill, SkillManager
from friday.plugins.commands import Command, CommandManager
from friday.plugins.hooks import Hook, HookManager, HookEvent
from friday.plugins.agents import AgentConfig, AgentManager
from friday.plugins.registry import PluginRegistry
from friday.plugins.analyzer import SkillAnalyzer, ConversionStrategy
from friday.plugins.converter import SkillConverter
from friday.plugins.importer import PluginImporter, ImportResult
from friday.plugins.sandbox import PluginManifest, PluginSandbox, PluginPermissionError
from friday.plugins.uninstaller import PluginUninstaller, UninstallTarget, UninstallResult

__all__ = [
    "Skill", "SkillManager",
    "Command", "CommandManager",
    "Hook", "HookManager", "HookEvent",
    "AgentConfig", "AgentManager",
    "PluginRegistry",
    "SkillAnalyzer", "ConversionStrategy",
    "SkillConverter",
    "PluginImporter", "ImportResult",
    "PluginManifest", "PluginSandbox", "PluginPermissionError",
    "PluginUninstaller", "UninstallTarget", "UninstallResult",
]
