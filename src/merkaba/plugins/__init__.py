# src/merkaba/plugins/__init__.py
"""Plugin system for Merkaba."""

from merkaba.plugins.skills import Skill, SkillManager
from merkaba.plugins.commands import Command, CommandManager
from merkaba.plugins.hooks import Hook, HookManager, HookEvent
from merkaba.plugins.agents import AgentConfig, AgentManager
from merkaba.plugins.registry import PluginRegistry
from merkaba.plugins.analyzer import SkillAnalyzer, ConversionStrategy
from merkaba.plugins.converter import SkillConverter
from merkaba.plugins.importer import PluginImporter, ImportResult
from merkaba.plugins.sandbox import PluginManifest, PluginSandbox, PluginPermissionError
from merkaba.plugins.uninstaller import PluginUninstaller, UninstallTarget, UninstallResult

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
